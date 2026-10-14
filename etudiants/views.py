# etudiants/views.py
import io, zipfile
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from django.db.models import Q

from .models import Etudiant, EtudiantDocument, Inscription, SanctionDisciplinaire
from .serializers import EtudiantSerializer, EtudiantDocumentSerializer, InscriptionSerializer
from academique.models import CourseAssignment
from academique.middleware import get_current_academic_year_id
from .views_situation import StudentSituationView, StudentHistoryView


# Liste + création
class EtudiantListCreateView(generics.ListCreateAPIView):
    serializer_class = EtudiantSerializer

    def get_queryset(self):
        queryset = Etudiant.objects.prefetch_related(
            'inscriptions__classe',
            'inscriptions__niveau',
            'inscriptions__annee_academique_ref',
            'documents',
            'sanctions',
        ).select_related('filiere', 'user')
        
        # Filtre global par année académique (via le header X-Academic-Year)
        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(inscriptions__annee_academique_ref_id=year_id)

        # Récupération des paramètres GET
        filiere_id = self.request.query_params.get("filiere")
        module_id = self.request.query_params.get("module")
        niveau_id = self.request.query_params.get("niveau")
        classe_id = self.request.query_params.get("classe")

        # Filtre par filière
        if filiere_id is not None and filiere_id.isdigit():
            queryset = queryset.filter(filiere_id=int(filiere_id))

        # Filtre par module (via CourseAssignment)
        if module_id is not None and module_id.isdigit():
            # Students in filieres where this module is assigned
            filiere_ids = CourseAssignment.objects.filter(module_id=int(module_id)).values_list('filiere_id', flat=True)
            queryset = queryset.filter(filiere_id__in=filiere_ids)
            
        # Filtre par niveau (via inscription)
        if niveau_id is not None and niveau_id.isdigit():
            queryset = queryset.filter(inscriptions__niveau_id=int(niveau_id))

        if classe_id is not None and classe_id.isdigit():
            queryset = queryset.filter(inscriptions__classe_id=int(classe_id))

        return queryset.distinct()


# Récupération + modification + suppression
class EtudiantRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Etudiant.objects.prefetch_related(
        'inscriptions__classe',
        'inscriptions__niveau',
        'inscriptions__annee_academique_ref',
        'documents',
        'sanctions',
    ).select_related('filiere', 'user')
    serializer_class = EtudiantSerializer


# --- Inscriptions ---
class InscriptionListCreateView(generics.ListCreateAPIView):
    queryset = Inscription.objects.all()
    serializer_class = InscriptionSerializer
    
    def get_queryset(self):
        queryset = Inscription.objects.all()
        
        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(annee_academique_ref_id=year_id)
            
        etudiant_id = self.request.query_params.get("etudiant")
        classe_id = self.request.query_params.get("classe")
        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if classe_id:
            queryset = queryset.filter(classe_id=classe_id)
        return queryset

class InscriptionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Inscription.objects.all()
    serializer_class = InscriptionSerializer


# Export des documents liés à un étudiant
class ExportEtudiantDocumentsView(APIView):
    def get(self, request, pk):
        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Etudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)

        documents = etudiant.documents.all()
        if not documents.exists():
            return Response({"error": "Aucun document trouvé pour cet étudiant"}, status=status.HTTP_404_NOT_FOUND)

        # Créer un ZIP en mémoire
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for doc in documents:
                zf.write(doc.fichier.path, arcname=doc.fichier.name.split("/")[-1])

        # Réponse HTTP avec le ZIP
        response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
        response['Content-Disposition'] = f'attachment; filename="documents_{etudiant.matricule}.zip"'
        return response


# Upload d’un document pour un étudiant (photo, CNI, acte, diplôme, etc.)
class EtudiantDocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Etudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)

        fichier = request.FILES.get("fichier")
        if not fichier:
            return Response({"error": "Aucun fichier reçu"}, status=status.HTTP_400_BAD_REQUEST)

        type_document = request.data.get("type_document", "Document")

        doc = EtudiantDocument.objects.create(
            etudiant=etudiant,
            fichier=fichier,
            type_document=type_document,
        )

        serializer = EtudiantDocumentSerializer(doc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# Validation de l'inscription finale
class ValiderInscriptionView(APIView):
    def post(self, request, pk):
        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Étudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)
        
        # Inscription à valider : celle demandée, sinon celle de l'année sélectionnée,
        # sinon la dernière pré-inscription.
        inscription_id = request.data.get("inscription_id") if hasattr(request, "data") else None
        inscriptions = etudiant.inscriptions.select_related("classe", "classe__filiere")
        inscription = None
        if inscription_id:
            inscription = inscriptions.filter(pk=inscription_id).first()
            if not inscription:
                return Response({"error": "Inscription introuvable pour cet étudiant."}, status=status.HTTP_404_NOT_FOUND)
        else:
            year_id = get_current_academic_year_id()
            if year_id:
                inscription = inscriptions.filter(annee_academique_ref_id=year_id).first()
            if not inscription:
                inscription = inscriptions.filter(statut='Pré-inscrit').order_by('-date_inscription', '-id').first()

        if inscription:
            if inscription.statut == 'Inscrit' and etudiant.statut == 'Inscrit':
                return Response({"message": "L'étudiant est déjà inscrit pour cette année."}, status=status.HTTP_400_BAD_REQUEST)
            inscription.statut = 'Inscrit'
            inscription.save(update_fields=['statut'])
            # La filière de l'étudiant suit la classe validée (changement d'orientation)
            if inscription.classe and inscription.classe.filiere_id and etudiant.filiere_id != inscription.classe.filiere_id:
                etudiant.filiere_id = inscription.classe.filiere_id
        elif etudiant.statut == 'Inscrit':
            return Response({"message": "L'étudiant est déjà inscrit."}, status=status.HTTP_400_BAD_REQUEST)

        etudiant.statut = 'Inscrit'
        etudiant.save()

        serializer = EtudiantSerializer(etudiant)
        return Response({
            "message": "Inscription validée avec succès.",
            "etudiant": serializer.data,
            "inscription": InscriptionSerializer(inscription).data if inscription else None,
        }, status=status.HTTP_200_OK)


class ReinscriptionView(APIView):
    """
    Pré-inscrit un étudiant existant pour une autre année académique (en général
    l'année suivante) dans une nouvelle classe. Le dossier (identité, matricule,
    documents, compte) est conservé : seule une nouvelle inscription est créée.
    """
    def post(self, request, pk):
        from academique.models import Classe

        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Étudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)

        classe_id = request.data.get("classe_id") or request.data.get("classe")
        if not classe_id:
            return Response({"error": "La classe de destination est requise."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            classe = Classe.objects.select_related("annee_academique", "niveau", "filiere").get(pk=classe_id)
        except (Classe.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Classe introuvable."}, status=status.HTTP_404_NOT_FOUND)

        if not classe.annee_academique_id:
            return Response({"error": "La classe choisie n'est rattachée à aucune année académique."}, status=status.HTTP_400_BAD_REQUEST)

        existante = etudiant.inscriptions.filter(annee_academique_ref_id=classe.annee_academique_id).first()
        if existante:
            return Response({
                "error": f"L'étudiant a déjà une inscription pour l'année {classe.annee_academique.libelle} ({existante.classe.nom if existante.classe else existante.niveau.nom}).",
            }, status=status.HTTP_400_BAD_REQUEST)

        inscription = Inscription.objects.create(
            etudiant=etudiant,
            classe=classe,
            niveau=classe.niveau,
            annee_academique=classe.annee_academique.libelle,
            annee_academique_ref=classe.annee_academique,
            statut='Pré-inscrit',
        )

        etudiant.refresh_from_db()
        return Response({
            "message": f"{etudiant.nom} est pré-inscrit(e) en {classe.nom} pour l'année {classe.annee_academique.libelle}.",
            "inscription": InscriptionSerializer(inscription).data,
            "etudiant": EtudiantSerializer(etudiant).data,
        }, status=status.HTTP_201_CREATED)

class MeEtudiantView(APIView):
    """
    Récupère le profil de l'étudiant actuellement connecté.
    """
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Non authentifié"}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            # Récupération via le related_name défini dans le modèle Etudiant
            etudiant = getattr(request.user, 'etudiant_profile', None)
            if not etudiant:
                return Response({"error": "Profil étudiant introuvable pour cet utilisateur"}, status=status.HTTP_404_NOT_FOUND)
            
            serializer = EtudiantSerializer(etudiant)
            return Response(serializer.data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StudentPortalViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet restreint pour les étudiants (Lecture seule).
    """
    serializer_class = EtudiantSerializer

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Etudiant.objects.none()
        return Etudiant.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil introuvable"}, status=404)
        serializer = self.get_serializer(etudiant)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="carte-etudiant")
    def carte_etudiant(self, request):
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil introuvable"}, status=404)
        
        # On renvoie les données pour que le front génère la carte
        data = {
            "nom": etudiant.nom,
            "matricule": etudiant.matricule,
            "filiere": etudiant.filiere.nom if etudiant.filiere else "N/A",
            "photo": None,
            "date_naissance": etudiant.date_naissance,
            "etablissement": "IFPT SMART CAMPUS",
        }
        # On cherche si une photo est uploadée
        photo = etudiant.documents.filter(type_document__icontains="Photo").first()
        if photo:
            data["photo"] = request.build_absolute_uri(photo.fichier.url)
            
        return Response(data)

    @action(detail=False, methods=["get"], url_path="certificat-scolarite")
    def certificat_scolarite(self, request):
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil introuvable"}, status=404)
            
        year_id = get_current_academic_year_id()
        if year_id:
            derniere_ins = etudiant.inscriptions.filter(annee_academique_ref_id=year_id).first()
        else:
            derniere_ins = etudiant.inscriptions.order_by("-date_inscription").first()

        if not derniere_ins:
             return Response({"error": "Aucune inscription active trouvée pour cette année"}, status=400)

        data = {
            "nom": etudiant.nom,
            "matricule": etudiant.matricule,
            "filiere": etudiant.filiere.nom if etudiant.filiere else "N/A",
            "niveau": derniere_ins.niveau.nom if derniere_ins.niveau else "N/A",
            "annee_academique": derniere_ins.annee_academique or "N/A",
            "date_emission": timezone.now().date(),
            "lieu": "Douala",
        }
        return Response(data)

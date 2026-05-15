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
        queryset = Etudiant.objects.all()
        
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
    queryset = Etudiant.objects.all()
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
        
        if etudiant.statut == 'Inscrit':
            return Response({"message": "L'étudiant est déjà inscrit."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Passer l'étudiant à Inscrit
        etudiant.statut = 'Inscrit'
        etudiant.save() 

        # Renvoyer la nouvelle data
        serializer = EtudiantSerializer(etudiant)
        return Response({
            "message": "Inscription validée avec succès.",
            "etudiant": serializer.data
        }, status=status.HTTP_200_OK)

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

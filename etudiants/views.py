# etudiants/views.py
import io, zipfile
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Etudiant, EtudiantDocument, Inscription
from .serializers import EtudiantSerializer, EtudiantDocumentSerializer, InscriptionSerializer


# Liste + création
class EtudiantListCreateView(generics.ListCreateAPIView):
    serializer_class = EtudiantSerializer

    def get_queryset(self):
        queryset = Etudiant.objects.all()

        # Récupération des paramètres GET
        filiere_id = self.request.query_params.get("filiere")
        module_id = self.request.query_params.get("module")
        niveau_id = self.request.query_params.get("niveau")
        classe_id = self.request.query_params.get("classe")

        # Filtre par filière
        if filiere_id is not None and filiere_id.isdigit():
            queryset = queryset.filter(filiere_id=int(filiere_id))

        # Filtre par module (via filière ou niveau)
        if module_id is not None and module_id.isdigit():
            # Si module lié à niveau lié à étudiant (via inscription actuelle ou historique)
            # Simplification : on garde le filtre par filière si besoin, mais ici on veut filtrer par module.
            # L'ancien code supposait filiere.modules.
            # Maintenant module est dans Niveau.
            # Mais Formation a encore modules (M2M) si on l'a gardé, ou on passe par Inscription.
            # Pour l'instant, on laisse tel quel si filiere.modules existe encore.
            queryset = queryset.filter(filiere__modules__id=int(module_id))
            
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
        etudiant.save()  # Déclenche la mise à jour de Revenu à 'Validé' et la création des notes (via signals)

        # Renvoyer la nouvelle data
        serializer = EtudiantSerializer(etudiant)
        return Response({
            "message": "Inscription validée avec succès. Facture validée et notes générées.",
            "etudiant": serializer.data
        }, status=status.HTTP_200_OK)

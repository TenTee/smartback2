# etudiants/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EtudiantListCreateView,
    EtudiantRetrieveUpdateDeleteView,
    ExportEtudiantDocumentsView,
    EtudiantDocumentUploadView,
    InscriptionListCreateView,
    InscriptionDetailView,
    ValiderInscriptionView,
    MeEtudiantView,
    StudentPortalViewSet,
)

router = DefaultRouter()
router.register(r'etudiants/portal', StudentPortalViewSet, basename='student-portal')

urlpatterns = [
    path("etudiants/me/", MeEtudiantView.as_view(), name="etudiant-me"),
    path("etudiants/", EtudiantListCreateView.as_view(), name="etudiant-list-create"),
    path("etudiants/<int:pk>/", EtudiantRetrieveUpdateDeleteView.as_view(), name="etudiant-detail"),
    path("etudiants/<int:pk>/export-documents/", ExportEtudiantDocumentsView.as_view(), name="etudiant-export-documents"),
    path("etudiants/<int:pk>/documents/", EtudiantDocumentUploadView.as_view(), name="etudiant-upload-document"),
    path("etudiants/<int:pk>/valider-inscription/", ValiderInscriptionView.as_view(), name="etudiant-valider-inscription"),
    
    path("inscriptions/", InscriptionListCreateView.as_view(), name="inscription-list-create"),
    path("inscriptions/<int:pk>/", InscriptionDetailView.as_view(), name="inscription-detail"),
    path("", include(router.urls)),
]
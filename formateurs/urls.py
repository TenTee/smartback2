# formateurs/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FormateurListCreateView,
    FormateurRetrieveUpdateDeleteView,
    FormateurGenerateAccountView,
    FormateurIdentifiantsView,
    FormateurPortalViewSet,
    CoursDocumentViewSet,
    CoursDocumentEtudiantView,
    FormateurSuiviView,
    FormateursSuiviListView,
)

router = DefaultRouter()
router.register(r'portal', FormateurPortalViewSet, basename='formateur-portal')
router.register(r'cours-documents', CoursDocumentViewSet, basename='cours-documents')

urlpatterns = [
    path('', FormateurListCreateView.as_view(), name='formateur-list'),
    path('suivi/', FormateursSuiviListView.as_view(), name='formateurs-suivi'),
    path('<int:pk>/suivi/', FormateurSuiviView.as_view(), name='formateur-suivi'),
    path('<int:pk>/', FormateurRetrieveUpdateDeleteView.as_view(), name='formateur-detail'),
    path('<int:pk>/identifiants/', FormateurIdentifiantsView.as_view(), name='formateur-identifiants'),
    path('<int:pk>/generate-account/', FormateurGenerateAccountView.as_view(), name='formateur-generate-account'),
    path('', include(router.urls)),
    path('cours-etudiants/', CoursDocumentEtudiantView.as_view(), name='cours-etudiants'),
]

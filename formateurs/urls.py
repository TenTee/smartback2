# formateurs/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FormateurListCreateView,
    FormateurRetrieveUpdateDeleteView,
    FormateurGenerateAccountView,
    FormateurPortalViewSet,
    CoursDocumentViewSet,
    CoursDocumentEtudiantView,
)

router = DefaultRouter()
router.register(r'portal', FormateurPortalViewSet, basename='formateur-portal')
router.register(r'cours-documents', CoursDocumentViewSet, basename='cours-documents')

urlpatterns = [
    path('', FormateurListCreateView.as_view(), name='formateur-list'),
    path('<int:pk>/', FormateurRetrieveUpdateDeleteView.as_view(), name='formateur-detail'),
    path('<int:pk>/generate-account/', FormateurGenerateAccountView.as_view(), name='formateur-generate-account'),
    path('', include(router.urls)),
    path('cours-etudiants/', CoursDocumentEtudiantView.as_view(), name='cours-etudiants'),
]

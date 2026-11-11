from django.urls import path
from rest_framework.routers import DefaultRouter

from .demandes import DemandeDocumentViewSet
from .views import DocumentDelivreViewSet, VerificationView

router = DefaultRouter()
router.register("documents-officiels", DocumentDelivreViewSet, basename="documents-officiels")
router.register("demandes-documents", DemandeDocumentViewSet, basename="demandes-documents")
urlpatterns = [
    path("documents-officiels/verifier/<str:code>/", VerificationView.as_view(), name="verifier-document"),
] + router.urls

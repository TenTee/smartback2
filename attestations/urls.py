from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DocumentDelivreViewSet, VerificationView

router = DefaultRouter()
router.register("documents-officiels", DocumentDelivreViewSet, basename="documents-officiels")
urlpatterns = [
    path("documents-officiels/verifier/<str:code>/", VerificationView.as_view(), name="verifier-document"),
] + router.urls

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DemandeAbsenceViewSet

router = DefaultRouter()
router.register(r"", DemandeAbsenceViewSet, basename="demande-absence")

urlpatterns = [
    path("", include(router.urls)),
]

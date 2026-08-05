from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PaieViewSet, ContentTypeView, PaieForecastView,
    PrimeViewSet, RetenueViewSet, AvanceSalaireViewSet,
    BulletinPaieViewSet, CampagnePaieViewSet,
    GenererCampagneView, ValiderCampagneView, PayerCampagneView,
    StatistiquesPaieView,
)

router = DefaultRouter()
router.register(r'paies', PaieViewSet, basename='paies')
router.register(r'primes', PrimeViewSet, basename='primes')
router.register(r'retenues', RetenueViewSet, basename='retenues')
router.register(r'avances', AvanceSalaireViewSet, basename='avances')
router.register(r'bulletins', BulletinPaieViewSet, basename='bulletins')
router.register(r'campagnes', CampagnePaieViewSet, basename='campagnes')

urlpatterns = [
    path('content-types/', ContentTypeView.as_view(), name="content-types"),
    path('forecast/', PaieForecastView.as_view(), name="paie-forecast"),
    path('campagnes/generer/', GenererCampagneView.as_view(), name="generer-campagne"),
    path('campagnes/<int:pk>/valider/', ValiderCampagneView.as_view(), name="valider-campagne"),
    path('campagnes/<int:pk>/payer/', PayerCampagneView.as_view(), name="payer-campagne"),
    path('statistiques/', StatistiquesPaieView.as_view(), name="statistiques-paie"),
    path('', include(router.urls)),
]

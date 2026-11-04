from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ArticleViewSet, BatimentViewSet, CampagneViewSet, EmplacementViewSet, ExemplaireViewSet, InterventionViewSet,
    InventaireStatsView, InventaireViewSet, MouvementStockViewSet, MouvementViewSet, SiteViewSet,
)

router = DefaultRouter()
router.register(r'articles', ArticleViewSet, basename='article')
router.register(r'exemplaires', ExemplaireViewSet, basename='exemplaire')
router.register(r'mouvements', MouvementViewSet, basename='mouvement')
router.register(r'mouvements-stock', MouvementStockViewSet, basename='mouvement-stock')
router.register(r'sites', SiteViewSet, basename='inventaire-site')
router.register(r'batiments', BatimentViewSet, basename='inventaire-batiment')
router.register(r'emplacements', EmplacementViewSet, basename='inventaire-emplacement')
router.register(r'interventions', InterventionViewSet, basename='inventaire-intervention')
router.register(r'campagnes', CampagneViewSet, basename='inventaire-campagne')
router.register(r'legacy', InventaireViewSet, basename='inventaire-legacy')

urlpatterns = [
    path('stats/', InventaireStatsView.as_view(), name='inventaire-stats'),
    path('', include(router.urls)),
]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ArticleViewSet, ExemplaireViewSet, MouvementViewSet,
    InventaireStatsView, InventaireViewSet,
)

router = DefaultRouter()
router.register(r'articles', ArticleViewSet, basename='article')
router.register(r'exemplaires', ExemplaireViewSet, basename='exemplaire')
router.register(r'mouvements', MouvementViewSet, basename='mouvement')
router.register(r'legacy', InventaireViewSet, basename='inventaire-legacy')

urlpatterns = [
    path('stats/', InventaireStatsView.as_view(), name='inventaire-stats'),
    path('', include(router.urls)),
]

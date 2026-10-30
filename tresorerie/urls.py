from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BudgetView, CategorieViewSet, ClotureViewSet, CompteViewSet, FournisseurViewSet, OperationViewSet, RapportsView,
    RapprochementViewSet, RecapAnneesView, TableauDeBordView,
)

router = DefaultRouter()
router.register("comptes", CompteViewSet, basename="tresorerie-comptes")
router.register("categories", CategorieViewSet, basename="tresorerie-categories")
router.register("fournisseurs", FournisseurViewSet, basename="tresorerie-fournisseurs")
router.register("operations", OperationViewSet, basename="tresorerie-operations")
router.register("clotures", ClotureViewSet, basename="tresorerie-clotures")
router.register("rapprochements", RapprochementViewSet, basename="tresorerie-rapprochements")

urlpatterns = [
    path("tableau-de-bord/", TableauDeBordView.as_view(), name="tresorerie-tableau-de-bord"),
    path("budget/", BudgetView.as_view(), name="tresorerie-budget"),
    path("rapports/", RapportsView.as_view(), name="tresorerie-rapports"),
    path("recap-annees/", RecapAnneesView.as_view(), name="tresorerie-recap-annees"),
] + router.urls

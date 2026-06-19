from django.urls import path
from .views import (
    DemandeListCreateView,
    DemandeRetrieveUpdateDeleteView,
    DemandeApprouverView,
    DemandeLivrerView,
    DemandeRefuserView,
    DemandeSoumettreView,
    LigneDemandeView,
    DemandesStatsView,
    DemandeursListView,
)

urlpatterns = [
    path("demandes/", DemandeListCreateView.as_view(), name="demande-list-create"),
    path("demandes/stats/", DemandesStatsView.as_view(), name="demandes-stats"),
    path("demandes/<int:pk>/", DemandeRetrieveUpdateDeleteView.as_view(), name="demande-detail"),
    path("demandes/<int:pk>/soumettre/", DemandeSoumettreView.as_view(), name="demande-soumettre"),
    path("demandes/<int:pk>/approuver/", DemandeApprouverView.as_view(), name="demande-approuver"),
    path("demandes/<int:pk>/livrer/", DemandeLivrerView.as_view(), name="demande-livrer"),
    path("demandes/<int:pk>/refuser/", DemandeRefuserView.as_view(), name="demande-refuser"),
    path("demandes/<int:pk>/lignes/", LigneDemandeView.as_view(), name="demande-lignes"),
    path("demandeurs/", DemandeursListView.as_view(), name="demandeurs-list"),
]

# demandes/urls.py
from django.urls import path
from .views import DemandeListCreateView, DemandeRetrieveUpdateDeleteView, DemandeursListView

urlpatterns = [
    path("demandes/", DemandeListCreateView.as_view(), name="demande-list-create"),
    path("demandes/<int:pk>/", DemandeRetrieveUpdateDeleteView.as_view(), name="demande-detail"),
    path("demandeurs/", DemandeursListView.as_view(), name="demandeurs-list"),
]
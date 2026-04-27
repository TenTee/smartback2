# formations/urls.py
from django.urls import path
from .views import FormationListCreateView, FormationRetrieveUpdateDeleteView, NiveauRetrieveUpdateView, NiveauListCreateView

urlpatterns = [
    path("formations/", FormationListCreateView.as_view(), name="formation-list-create"),
    path("formations/<int:pk>/", FormationRetrieveUpdateDeleteView.as_view(), name="formation-detail"),
    path("niveaux/", NiveauListCreateView.as_view(), name="niveau-list-create"),
    path("niveaux/<int:pk>/", NiveauRetrieveUpdateView.as_view(), name="niveau-detail"),
]
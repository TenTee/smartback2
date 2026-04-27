from rest_framework import viewsets, filters

from django_filters.rest_framework import DjangoFilterBackend
from .models import Revenu
from .serializers import RevenuSerializer

class RevenuViewSet(viewsets.ModelViewSet):
    queryset = Revenu.objects.all().order_by("-date_entree")
    serializer_class = RevenuSerializer
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["categorie", "statut"]
    search_fields = ["libelle", "responsable"]


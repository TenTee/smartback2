# recufactures/views.py
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend

from .models import Depense
from .serializers import DepenseSerializer

class DepenseViewSet(viewsets.ModelViewSet):
    queryset = Depense.objects.all()
    serializer_class = DepenseSerializer

    # ✅ Ajout des filtres
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['categorie', 'statut']
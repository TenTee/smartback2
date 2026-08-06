from rest_framework import viewsets

from .models import DemandeAbsence
from .serializers import DemandeAbsenceSerializer


class DemandeAbsenceViewSet(viewsets.ModelViewSet):
    queryset = DemandeAbsence.objects.all()
    serializer_class = DemandeAbsenceSerializer

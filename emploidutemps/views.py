from rest_framework import viewsets, filters, serializers
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import EmploiDuTemps
from .serializers import EmploiDuTempsSerializer

class EmploiDuTempsViewSet(viewsets.ModelViewSet):
    queryset = EmploiDuTemps.objects.all()
    serializer_class = EmploiDuTempsSerializer

    # 🔎 Ajout de filtres et recherche
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["jour", "formation", "niveau", "classe", "formateur", "module", "salle"]
    search_fields = ["salle", "formation__intitule", "formateur__nom", "module__nom"]
    ordering_fields = ["heure_debut", "heure_fin"]

    def perform_create(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError({"non_field_errors": e.messages})

    def perform_update(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as e:
            raise serializers.ValidationError({"non_field_errors": e.messages})

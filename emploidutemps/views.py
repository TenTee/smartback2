from rest_framework import viewsets, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from .models import EmploiDuTemps
from .serializers import EmploiDuTempsSerializer

class EmploiDuTempsViewSet(viewsets.ModelViewSet):
    queryset = EmploiDuTemps.objects.all()
    serializer_class = EmploiDuTempsSerializer

    # 🔎 Ajout de filtres et recherche
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["jour", "filiere", "niveau", "classe", "formateur", "module", "salle"]
    search_fields = ["salle", "filiere__nom", "formateur__nom", "module__nom"]
    ordering_fields = ["heure_debut", "heure_fin"]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Récupère l'emploi du temps de l'étudiant connecté."""
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil étudiant introuvable"}, status=404)
        
        # On récupère les emplois du temps liés à la classe de l'étudiant
        classe_ids = etudiant.inscriptions.values_list('classe_id', flat=True)
        niveau_ids = etudiant.inscriptions.values_list('niveau_id', flat=True)
        
        queryset = EmploiDuTemps.objects.filter(
            models.Q(classe_id__in=classe_ids) | 
            models.Q(niveau_id__in=niveau_ids, classe__isnull=True)
        )
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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

from rest_framework import viewsets, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from .models import EmploiDuTemps, Salle, periode_q, semaine_de
from .serializers import EmploiDuTempsSerializer, SalleSerializer

class SalleViewSet(viewsets.ModelViewSet):
    queryset = Salle.objects.all()
    serializer_class = SalleSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nom", "description"]
    ordering_fields = ["nom"]

class EmploiDuTempsViewSet(viewsets.ModelViewSet):
    queryset = EmploiDuTemps.objects.all()
    serializer_class = EmploiDuTempsSerializer

    # 🔎 Ajout de filtres et recherche
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["jour", "filiere", "niveau", "classe", "formateur", "module", "salle"]
    search_fields = ["salle__nom", "filiere__nom", "formateur__nom", "module__nom"]
    ordering_fields = ["heure_debut", "heure_fin"]

    @staticmethod
    def _parse_date(value):
        from django.utils.dateparse import parse_date
        try:
            return parse_date(value) if value else None
        except (TypeError, ValueError):
            return None

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        # ?date_debut=YYYY-MM-DD&date_fin=YYYY-MM-DD → créneaux de cette période (+ permanents)
        # ?date=YYYY-MM-DD → créneaux de la semaine contenant cette date
        date_debut = self._parse_date(params.get("date_debut"))
        date_fin = self._parse_date(params.get("date_fin"))
        jour = self._parse_date(params.get("date"))
        if jour and not (date_debut or date_fin):
            date_debut, date_fin = semaine_de(jour)
        if self.action == "list" and (date_debut or date_fin):
            queryset = queryset.filter(periode_q(date_debut, date_fin))
        return queryset

    @action(detail=False, methods=["post"], url_path="dupliquer")
    def dupliquer(self, request):
        """
        Copie les créneaux d'une période vers une autre (ex. semaine suivante).
        Corps : source_debut, source_fin, cible_debut, cible_fin, classe (optionnel), remplacer (bool).
        """
        from django.db import transaction
        data = request.data
        source_debut = self._parse_date(data.get("source_debut"))
        source_fin = self._parse_date(data.get("source_fin"))
        cible_debut = self._parse_date(data.get("cible_debut"))
        cible_fin = self._parse_date(data.get("cible_fin"))
        if not (source_debut and source_fin and cible_debut and cible_fin):
            return Response({"error": "Les périodes source et cible sont requises (YYYY-MM-DD)."}, status=400)
        if cible_fin < cible_debut:
            return Response({"error": "La période cible est invalide."}, status=400)

        source = EmploiDuTemps.objects.filter(date_debut=source_debut, date_fin=source_fin)
        cible = EmploiDuTemps.objects.filter(date_debut=cible_debut, date_fin=cible_fin)
        classe_id = data.get("classe")
        if classe_id:
            source = source.filter(classe_id=classe_id)
            cible = cible.filter(classe_id=classe_id)
        if not source.exists():
            return Response({"error": "Aucun créneau à copier sur la période source."}, status=400)

        crees, erreurs = 0, []
        with transaction.atomic():
            if str(data.get("remplacer", "")).lower() in ("1", "true", "yes", "oui"):
                for old in cible:
                    super(EmploiDuTemps, old).delete()
            for ed in source.select_related("module", "classe"):
                copie = EmploiDuTemps(
                    filiere_id=ed.filiere_id, niveau_id=ed.niveau_id, classe_id=ed.classe_id,
                    module_id=ed.module_id, formateur_id=ed.formateur_id, jour=ed.jour,
                    heure_debut=ed.heure_debut, heure_fin=ed.heure_fin, salle_id=ed.salle_id,
                    date_debut=cible_debut, date_fin=cible_fin,
                )
                try:
                    copie.save()
                    crees += 1
                except DjangoValidationError as e:
                    erreurs.append(f"{ed.jour} {ed.heure_debut:%H:%M}-{ed.heure_fin:%H:%M} {ed.module.nom} : {' '.join(e.messages)}")
        return Response({"crees": crees, "erreurs": erreurs}, status=201 if crees else 400)

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
        # Par défaut : la semaine en cours (ou celle de ?date=YYYY-MM-DD) + les créneaux permanents
        from django.utils import timezone
        jour = self._parse_date(request.query_params.get("date")) or timezone.localdate()
        queryset = queryset.filter(periode_q(*semaine_de(jour)))
        
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

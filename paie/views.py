from rest_framework import viewsets, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.utils import timezone
from datetime import date

from .models import Paie, ParametresPaie
from .serializers import PaieSerializer
from personnels.models import Personnel
from formateurs.models import Formateur

class PaieViewSet(viewsets.ModelViewSet):
    """
    CRUD pour les paies
    """
    queryset = Paie.objects.all().order_by('-date')
    serializer_class = PaieSerializer

class PaieForecastView(APIView):
    """
    Vue pour les prévisions de paie et la configuration du jour de paie.
    """
    def get(self, request):
        today = timezone.now().date()
        month = today.month
        year = today.year

        # 1. Calcul du total des salaires configurés (Prévision)
        total_personnel = Personnel.objects.aggregate(total=Sum('salaire'))['total'] or 0
        total_formateurs = Formateur.objects.aggregate(total=Sum('salaire'))['total'] or 0
        total_previsionnel = total_personnel + total_formateurs

        # 2. Calcul de ce qui a déjà été payé ce mois-ci
        total_paye = Paie.objects.filter(
            date__month=month, 
            date__year=year, 
            statut="Payé"
        ).aggregate(total=Sum('salaire'))['total'] or 0

        # 3. Récupération du jour de paie
        config = ParametresPaie.objects.first()
        jour_paie = config.jour_de_paie if config else 25

        # 4. Prochaine échéance
        prochaine_paie = date(year, month, jour_paie)
        if today > prochaine_paie:
            # Si le jour est passé, on prévoit pour le mois prochain
            if month == 12:
                prochaine_paie = date(year + 1, 1, jour_paie)
            else:
                prochaine_paie = date(year, month + 1, jour_paie)

        return Response({
            "total_previsionnel": total_previsionnel,
            "total_paye_mois": total_paye,
            "reste_a_payer": max(0, total_previsionnel - total_paye),
            "jour_de_paie": jour_paie,
            "prochaine_echeance": prochaine_paie,
            "is_near_payday": (prochaine_paie - today).days <= 5 and (prochaine_paie - today).days >= 0
        })

    def post(self, request):
        # Mise à jour du jour de paie
        jour = request.data.get("jour_de_paie")
        if jour is not None:
            config, created = ParametresPaie.objects.get_or_create(id=1)
            config.jour_de_paie = int(jour)
            config.save()
            return Response({"message": "Jour de paie mis à jour", "jour_de_paie": config.jour_de_paie})
        return Response({"error": "Données invalides"}, status=400)

class ContentTypeView(APIView):
    """
    Expose les IDs ContentType pour Personnel et Formateur
    """
    def get(self, request):
        return Response({
            "personnel": ContentType.objects.get(app_label="personnels", model="personnel").id,
            "formateur": ContentType.objects.get(app_label="formateurs", model="formateur").id,
        })
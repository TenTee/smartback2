from django.db.models import Max, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from etudiants.models import Etudiant

from .models import (
    FormationPaymentPolicy,
    Paiement,
    StudentPaymentInstallment,
    StudentPaymentPlan,
)
from .serializers import (
    FormationPaymentPolicySerializer,
    PaiementAggregatedSerializer,
    PaiementSerializer,
    PaymentAlertSerializer,
    StudentPaymentPlanSerializer,
)


class PaiementListCreate(generics.ListCreateAPIView):
    serializer_class = PaiementSerializer

    def get_queryset(self):
        queryset = Paiement.objects.select_related("etudiant", "formation", "frais", "frais__classe").all()
        etudiant_id = self.request.query_params.get("etudiant")
        frais_id = self.request.query_params.get("frais")
        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if frais_id:
            queryset = queryset.filter(frais_id=frais_id)
        return queryset.order_by("-date_paiement")


class PaiementDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Paiement.objects.select_related("etudiant", "formation", "frais", "frais__classe").all()
    serializer_class = PaiementSerializer


class PaiementAggregated(APIView):
    def get(self, request):
        etudiants = Etudiant.objects.select_related("filiere")
        results = []
        for etudiant in etudiants:
            paiements = Paiement.objects.filter(etudiant=etudiant, formation=etudiant.filiere)
            paiements_inscription = paiements.filter(paiement_type="INSCRIPTION")
            paiements_formation = paiements.filter(paiement_type="FORMATION")

            montant_paye_total = paiements.aggregate(
                total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
            )["total"]
            montant_paye_inscription_total = paiements_inscription.aggregate(
                total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
            )["total"]
            montant_paye_formation_total = paiements_formation.aggregate(
                total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
            )["total"]
            derniere_date = paiements.aggregate(last=Max("date_paiement"))["last"]

            montant_du_inscription = getattr(etudiant.filiere, "frais_inscription", 0)
            montant_du_formation = getattr(etudiant.filiere, "montant", 0)
            solde_inscription = float(montant_du_inscription) - float(montant_paye_inscription_total)
            solde_formation = float(montant_du_formation) - float(montant_paye_formation_total)
            solde = float(montant_du_inscription + montant_du_formation) - float(montant_paye_total)

            results.append(
                {
                    "etudiant": etudiant.id,
                    "etudiant_nom": etudiant.nom,
                    "formation": etudiant.filiere.id,
                    "formation_nom": etudiant.filiere.intitule,
                    "montant_du": float(montant_du_inscription + montant_du_formation),
                    "montant_paye_total": montant_paye_total,
                    "solde_restant": solde,
                    "montant_du_inscription": montant_du_inscription,
                    "montant_paye_inscription_total": montant_paye_inscription_total,
                    "solde_restant_inscription": solde_inscription,
                    "montant_du_formation": montant_du_formation,
                    "montant_paye_formation_total": montant_paye_formation_total,
                    "solde_restant_formation": solde_formation,
                    "derniere_date": derniere_date,
                }
            )

        serializer = PaiementAggregatedSerializer(results, many=True)
        return Response(serializer.data)


class FormationPaymentPolicyListCreateView(generics.ListCreateAPIView):
    queryset = FormationPaymentPolicy.objects.select_related("formation").prefetch_related("four_installments").all()
    serializer_class = FormationPaymentPolicySerializer


class FormationPaymentPolicyDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = FormationPaymentPolicy.objects.select_related("formation").prefetch_related("four_installments").all()
    serializer_class = FormationPaymentPolicySerializer


class StudentPaymentPlanListCreateView(generics.ListCreateAPIView):
    serializer_class = StudentPaymentPlanSerializer

    def get_queryset(self):
        queryset = StudentPaymentPlan.objects.select_related("etudiant", "formation", "policy").prefetch_related("installments").all()
        etudiant_id = self.request.query_params.get("etudiant")
        formation_id = self.request.query_params.get("formation")
        status_value = self.request.query_params.get("status")
        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if formation_id:
            queryset = queryset.filter(formation_id=formation_id)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset


class StudentPaymentPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StudentPaymentPlan.objects.select_related("etudiant", "formation", "policy").prefetch_related("installments").all()
    serializer_class = StudentPaymentPlanSerializer


class PaymentAlertListView(APIView):
    def get(self, request):
        today = timezone.localdate()
        etudiant_id = request.query_params.get("etudiant")
        formation_id = request.query_params.get("formation")

        installments = StudentPaymentInstallment.objects.select_related("plan", "plan__etudiant", "plan__formation").all()
        if etudiant_id:
            installments = installments.filter(plan__etudiant_id=etudiant_id)
        if formation_id:
            installments = installments.filter(plan__formation_id=formation_id)

        alerts = []
        for installment in installments:
            installment.refresh_status(today)
            balance_due = installment.balance_due
            if balance_due <= 0:
                continue

            alert_threshold = installment.plan.alert_days_before or 0
            days_until_due = (installment.due_date - today).days
            if installment.status == StudentPaymentInstallment.STATUS_OVERDUE:
                severity = "high"
                message = f"Echeance depassee de {abs(days_until_due)} jour(s)."
            elif days_until_due <= alert_threshold:
                severity = "medium"
                message = f"Echeance a venir dans {days_until_due} jour(s)."
            else:
                continue

            alerts.append(
                {
                    "plan_id": installment.plan_id,
                    "etudiant_id": installment.plan.etudiant_id,
                    "etudiant_nom": installment.plan.etudiant.nom,
                    "formation_id": installment.plan.formation_id,
                    "formation_nom": installment.plan.formation.intitule,
                    "installment_id": installment.id,
                    "label": installment.label,
                    "due_date": installment.due_date,
                    "amount_due": installment.amount_due,
                    "amount_paid": installment.amount_paid,
                    "balance_due": balance_due,
                    "status": installment.status,
                    "severity": severity,
                    "message": message,
                }
            )

        serializer = PaymentAlertSerializer(alerts, many=True)
        return Response(serializer.data)

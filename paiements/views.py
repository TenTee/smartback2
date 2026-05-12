from decimal import Decimal
from django.db.models import Max, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from etudiants.models import Etudiant
from academique.middleware import get_current_academic_year_id

from .models import (
    FilierePaymentPolicy,
    Frais,
    Paiement,
    StudentPaymentInstallment,
    StudentPaymentPlan,
)
from .serializers import (
    FilierePaymentPolicySerializer,
    PaiementAggregatedSerializer,
    PaiementSerializer,
    PaymentAlertSerializer,
    StudentPaymentPlanSerializer,
)


class PaiementListCreate(generics.ListCreateAPIView):
    serializer_class = PaiementSerializer

    def get_queryset(self):
        queryset = Paiement.objects.select_related("etudiant", "filiere", "frais", "frais__classe").all()
        
        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(frais__classe__annee_academique_id=year_id)

        etudiant_id = self.request.query_params.get("etudiant")
        frais_id = self.request.query_params.get("frais")
        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if frais_id:
            queryset = queryset.filter(frais_id=frais_id)
        return queryset.order_by("-date_paiement")


class PaiementDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Paiement.objects.select_related("etudiant", "filiere", "frais", "frais__classe").all()
    serializer_class = PaiementSerializer


class PaiementAggregated(APIView):
    def get(self, request):
        etudiants = Etudiant.objects.select_related("filiere").prefetch_related("inscriptions", "inscriptions__classe")
        
        year_id = get_current_academic_year_id()
        if year_id:
            etudiants = etudiants.filter(inscriptions__annee_academique_ref_id=year_id).distinct()

        results = []
        for etudiant in etudiants:
            # Récupérer l'inscription active (la plus récente)
            derniere_inscription = etudiant.inscriptions.order_by("-date_inscription").first()
            
            classe = derniere_inscription.classe if derniere_inscription else None
            
            # Calculer les frais dûs
            montant_du_inscription = Decimal("0")
            montant_du_formation = Decimal("0")
            
            if classe:
                frais_classe = Frais.objects.filter(classe=classe)
                frais_inscription = frais_classe.filter(libelle__icontains="inscription")
                frais_formation = frais_classe.exclude(libelle__icontains="inscription")
                
                montant_du_inscription = frais_inscription.aggregate(total=Coalesce(Sum("montant"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))))["total"]
                montant_du_formation = frais_formation.aggregate(total=Coalesce(Sum("montant"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))))["total"]
            
            # Calculer les paiements effectués
            paiements = Paiement.objects.filter(etudiant=etudiant)
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

            solde_inscription = float(montant_du_inscription) - float(montant_paye_inscription_total)
            solde_formation = float(montant_du_formation) - float(montant_paye_formation_total)
            solde = float(montant_du_inscription + montant_du_formation) - float(montant_paye_total)

            results.append(
                {
                    "etudiant": etudiant.id,
                    "etudiant_nom": etudiant.nom,
                    "formation": etudiant.filiere.id if etudiant.filiere else 0,
                    "formation_nom": etudiant.filiere.nom if etudiant.filiere else "N/A",
                    "montant_du": float(montant_du_inscription + montant_du_formation),
                    "montant_paye_total": montant_paye_total,
                    "solde_restant": solde,
                    "montant_du_inscription": float(montant_du_inscription),
                    "montant_paye_inscription_total": float(montant_paye_inscription_total),
                    "solde_restant_inscription": solde_inscription,
                    "montant_du_formation": float(montant_du_formation),
                    "montant_paye_formation_total": float(montant_paye_formation_total),
                    "solde_restant_formation": solde_formation,
                    "derniere_date": derniere_date,
                }
            )

        serializer = PaiementAggregatedSerializer(results, many=True)
        return Response(serializer.data)


class FilierePaymentPolicyListCreateView(generics.ListCreateAPIView):
    queryset = FilierePaymentPolicy.objects.select_related("filiere").prefetch_related("four_installments").all()
    serializer_class = FilierePaymentPolicySerializer


class FilierePaymentPolicyDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = FilierePaymentPolicy.objects.select_related("filiere").prefetch_related("four_installments").all()
    serializer_class = FilierePaymentPolicySerializer


class StudentPaymentPlanListCreateView(generics.ListCreateAPIView):
    serializer_class = StudentPaymentPlanSerializer

    def get_queryset(self):
        queryset = StudentPaymentPlan.objects.select_related("etudiant", "filiere", "policy").prefetch_related("installments").all()
        
        year_id = get_current_academic_year_id()
        if year_id:
            # Plans don't have year directly, but we can filter via etudiant inscriptions
            queryset = queryset.filter(etudiant__inscriptions__annee_academique_ref_id=year_id).distinct()

        etudiant_id = self.request.query_params.get("etudiant")
        filiere_id = self.request.query_params.get("filiere")
        status_value = self.request.query_params.get("status")
        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if filiere_id:
            queryset = queryset.filter(filiere_id=filiere_id)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset


class StudentPaymentPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StudentPaymentPlan.objects.select_related("etudiant", "filiere", "policy").prefetch_related("installments").all()
    serializer_class = StudentPaymentPlanSerializer


class PaymentAlertListView(APIView):
    def get(self, request):
        today = timezone.localdate()
        etudiant_id = request.query_params.get("etudiant")
        filiere_id = request.query_params.get("filiere")

        installments = StudentPaymentInstallment.objects.select_related("plan", "plan__etudiant", "plan__filiere").all()
        
        year_id = get_current_academic_year_id()
        if year_id:
            installments = installments.filter(plan__etudiant__inscriptions__annee_academique_ref_id=year_id).distinct()

        if etudiant_id:
            installments = installments.filter(plan__etudiant_id=etudiant_id)
        if filiere_id:
            installments = installments.filter(plan__filiere_id=filiere_id)

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
                    "formation_id": installment.plan.filiere_id,
                    "formation_nom": installment.plan.filiere.nom,
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

from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication

class MePaiementSummary(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]
    """
    Retourne un résumé financier pour l'étudiant connecté.
    """
    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"error": "Authentification requise"}, status=status.HTTP_401_UNAUTHORIZED)
            
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil étudiant introuvable"}, status=404)

        year_id = get_current_academic_year_id()
        if year_id:
            derniere_inscription = etudiant.inscriptions.filter(annee_academique_ref_id=year_id).first()
        else:
            derniere_inscription = etudiant.inscriptions.order_by("-date_inscription").first()
            
        classe = derniere_inscription.classe if derniere_inscription else None
        
        montant_du_inscription = Decimal("0")
        montant_du_formation = Decimal("0")
        if classe:
            frais_classe = Frais.objects.filter(classe=classe)
            montant_du_inscription = frais_classe.filter(libelle__icontains="inscription").aggregate(
                total=Coalesce(Sum("montant"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
            )["total"]
            montant_du_formation = frais_classe.exclude(libelle__icontains="inscription").aggregate(
                total=Coalesce(Sum("montant"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
            )["total"]
        
        paiements = Paiement.objects.filter(etudiant=etudiant)
        montant_paye_inscription = paiements.filter(paiement_type="INSCRIPTION").aggregate(
            total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
        )["total"]
        montant_paye_formation = paiements.filter(paiement_type="FORMATION").aggregate(
            total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
        )["total"]

        plan = StudentPaymentPlan.objects.filter(etudiant=etudiant).first()
        installments = []
        if plan:
            for inst in plan.installments.all():
                installments.append({
                    "label": inst.label,
                    "due_date": inst.due_date,
                    "amount_due": inst.amount_due,
                    "amount_paid": inst.amount_paid,
                    "status": inst.status
                })

        return Response({
            "inscription": {
                "du": float(montant_du_inscription),
                "paye": float(montant_paye_inscription),
                "reste": float(montant_du_inscription - montant_paye_inscription)
            },
            "formation": {
                "du": float(montant_du_formation),
                "paye": float(montant_paye_formation),
                "reste": float(montant_du_formation - montant_paye_formation)
            },
            "echeances": installments
        })

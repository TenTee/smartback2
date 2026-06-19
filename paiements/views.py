from decimal import Decimal
from django.db import models
from django.db.models import Max, Sum, Value, DecimalField, Count
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
            queryset = queryset.filter(
                models.Q(frais__classe__annee_academique_id=year_id) | models.Q(frais__isnull=True)
            )

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
            # Récupérer l'inscription de l'année en cours
            if year_id:
                derniere_inscription = etudiant.inscriptions.filter(annee_academique_ref_id=year_id).first()
            else:
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

            # Calculer les paiements effectués (inclure ceux avec et sans frais)
            paiements = Paiement.objects.filter(etudiant=etudiant)
            if year_id:
                paiements = paiements.filter(
                    models.Q(frais__classe__annee_academique_id=year_id) | models.Q(frais__isnull=True)
                )
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

class FinancialDashboardView(APIView):
    """
    Dashboard financier global avec toutes les métriques clés.
    """
    def get(self, request):
        year_id = get_current_academic_year_id()

        # Étudiants inscrits cette année
        etudiants_qs = Etudiant.objects.all()
        if year_id:
            etudiants_qs = etudiants_qs.filter(inscriptions__annee_academique_ref_id=year_id).distinct()
        total_etudiants = etudiants_qs.count()

        # Calcul total des frais attendus
        from academique.models import Classe
        classes_qs = Classe.objects.all()
        if year_id:
            classes_qs = classes_qs.filter(annee_academique_id=year_id)

        total_attendu_inscription = Decimal("0")
        total_attendu_formation = Decimal("0")
        total_recouvre_inscription = Decimal("0")
        total_recouvre_formation = Decimal("0")

        for etudiant in etudiants_qs:
            derniere_inscription = etudiant.inscriptions.order_by("-date_inscription").first()
            if year_id:
                derniere_inscription = etudiant.inscriptions.filter(annee_academique_ref_id=year_id).first()
            classe = derniere_inscription.classe if derniere_inscription else None
            if classe:
                frais_classe = Frais.objects.filter(classe=classe)
                total_attendu_inscription += frais_classe.filter(
                    libelle__icontains="inscription"
                ).aggregate(t=Sum("montant"))["t"] or Decimal("0")
                total_attendu_formation += frais_classe.exclude(
                    libelle__icontains="inscription"
                ).aggregate(t=Sum("montant"))["t"] or Decimal("0")

        # Montants recouvrés
        paiements_qs = Paiement.objects.all()
        if year_id:
            paiements_qs = paiements_qs.filter(
                models.Q(frais__classe__annee_academique_id=year_id) | models.Q(frais__isnull=True)
            )

        total_recouvre_inscription = paiements_qs.filter(
            paiement_type="INSCRIPTION"
        ).aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")
        total_recouvre_formation = paiements_qs.filter(
            paiement_type="FORMATION"
        ).aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")

        total_attendu = total_attendu_inscription + total_attendu_formation
        total_recouvre = total_recouvre_inscription + total_recouvre_formation
        taux_recouvrement = (float(total_recouvre) / float(total_attendu) * 100) if total_attendu > 0 else 0

        # Étudiants par statut de paiement
        etudiants_soldes = 0
        etudiants_partiels = 0
        etudiants_non_payes = 0
        for etudiant in etudiants_qs:
            total_du = Decimal("0")
            derniere_inscription = etudiant.inscriptions.order_by("-date_inscription").first()
            if year_id:
                derniere_inscription = etudiant.inscriptions.filter(annee_academique_ref_id=year_id).first()
            classe = derniere_inscription.classe if derniere_inscription else None
            if classe:
                total_du = Frais.objects.filter(classe=classe).aggregate(t=Sum("montant"))["t"] or Decimal("0")

            total_paye = Paiement.objects.filter(etudiant=etudiant).aggregate(
                t=Sum("montant_paye"))["t"] or Decimal("0")

            if total_du > 0:
                if total_paye >= total_du:
                    etudiants_soldes += 1
                elif total_paye > 0:
                    etudiants_partiels += 1
                else:
                    etudiants_non_payes += 1
            else:
                etudiants_non_payes += 1

        # Paiements récents (7 derniers jours)
        from datetime import timedelta
        seven_days_ago = timezone.now() - timedelta(days=7)
        paiements_recents = paiements_qs.filter(date_paiement__gte=seven_days_ago).count()
        montant_recents = paiements_qs.filter(
            date_paiement__gte=seven_days_ago
        ).aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")

        # Répartition par moyen de paiement
        repartition_moyens = []
        for moyen_code, moyen_label in Paiement.MOYENS:
            total = paiements_qs.filter(moyen_paiement=moyen_code).aggregate(t=Sum("montant_paye"))["t"] or 0
            count = paiements_qs.filter(moyen_paiement=moyen_code).count()
            if count > 0:
                repartition_moyens.append({
                    "moyen": moyen_label,
                    "code": moyen_code,
                    "montant": float(total),
                    "nombre": count,
                })

        # Paiements par mois (historique)
        from django.db.models.functions import TruncMonth, ExtractMonth, ExtractYear
        paiements_par_mois = (
            paiements_qs
            .annotate(mois=ExtractMonth('date_paiement'), annee=ExtractYear('date_paiement'))
            .values('mois', 'annee')
            .annotate(total=Sum('montant_paye'), nombre=models.Count('id'))
            .order_by('annee', 'mois')
        )

        # Alertes
        today = timezone.localdate()
        installments_overdue = StudentPaymentInstallment.objects.filter(
            status=StudentPaymentInstallment.STATUS_OVERDUE
        )
        if year_id:
            installments_overdue = installments_overdue.filter(
                plan__etudiant__inscriptions__annee_academique_ref_id=year_id
            ).distinct()
        nb_echeances_retard = installments_overdue.count()
        montant_echeances_retard = sum(i.balance_due for i in installments_overdue)

        # Répartition par filière
        from academique.models import Filiere as FiliereModel
        repartition_filieres = []
        filieres = FiliereModel.objects.all()
        for filiere in filieres:
            etudiants_filiere = etudiants_qs.filter(filiere=filiere)
            nb_etudiants = etudiants_filiere.count()
            if nb_etudiants == 0:
                continue
            total_paye_filiere = Paiement.objects.filter(
                etudiant__in=etudiants_filiere
            ).aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")
            repartition_filieres.append({
                "filiere": filiere.nom,
                "nb_etudiants": nb_etudiants,
                "total_recouvre": float(total_paye_filiere),
            })

        return Response({
            "total_etudiants": total_etudiants,
            "total_attendu": float(total_attendu),
            "total_attendu_inscription": float(total_attendu_inscription),
            "total_attendu_formation": float(total_attendu_formation),
            "total_recouvre": float(total_recouvre),
            "total_recouvre_inscription": float(total_recouvre_inscription),
            "total_recouvre_formation": float(total_recouvre_formation),
            "solde_global": float(total_attendu - total_recouvre),
            "taux_recouvrement": round(taux_recouvrement, 1),
            "etudiants_soldes": etudiants_soldes,
            "etudiants_partiels": etudiants_partiels,
            "etudiants_non_payes": etudiants_non_payes,
            "paiements_7j": paiements_recents,
            "montant_7j": float(montant_recents),
            "repartition_moyens": repartition_moyens,
            "paiements_par_mois": list(paiements_par_mois),
            "nb_echeances_retard": nb_echeances_retard,
            "montant_echeances_retard": float(montant_echeances_retard),
            "repartition_filieres": repartition_filieres,
        })


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

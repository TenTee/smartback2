from decimal import Decimal
from django.db import models
from django.db.models import Max, Sum, Value, DecimalField, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.db import transaction
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from etudiants.models import Etudiant
from academique.middleware import get_current_academic_year_id

from .models import paiements_de_l_annee
from .models import (
    ClassePaymentInstallment,
    ClassePaymentSchedule,
    FilierePaymentPolicy,
    Frais,
    Paiement,
    StudentPaymentInstallment,
    StudentPaymentPlan,
    recalculer_echeancier,
)
from .serializers import (
    ClassePaymentScheduleSerializer,
    FilierePaymentPolicySerializer,
    PaiementAggregatedSerializer,
    PaiementSerializer,
    PaymentAlertSerializer,
    ResolvedScheduleSerializer,
    StudentPaymentPlanSerializer,
)
from .schedule_resolver import compute_student_retard
from .frais_etudiant import frais_etudiant


class PaiementListCreate(generics.ListCreateAPIView):
    serializer_class = PaiementSerializer

    def get_queryset(self):
        queryset = Paiement.objects.select_related("etudiant", "filiere", "frais", "frais__classe").all()

        year_id = get_current_academic_year_id()
        queryset = paiements_de_l_annee(queryset, year_id)

        etudiant_id = self.request.query_params.get("etudiant")
        frais_id = self.request.query_params.get("frais")
        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if frais_id:
            queryset = queryset.filter(frais_id=frais_id)
        return queryset.order_by("-date_paiement")


class _EcritureFinance(BasePermission):
    """Lecture : tout utilisateur connecté. Modification / suppression : droit Finances en écriture."""
    message = "Seul un utilisateur avec le droit Finances en écriture peut modifier ou supprimer un paiement."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        from tresorerie.views import DroitFinance
        return DroitFinance().has_permission(request, view)


def _nom(user):
    return f"{getattr(user, 'prenoms', '') or ''} {getattr(user, 'noms', '') or ''}".strip() or getattr(user, "username", "")


def _controler_tresorerie(paiement, nouveau_compte=None):
    """Refuse la modification d'un paiement déjà rapproché ou compris dans une caisse clôturée."""
    from tresorerie.models import Operation
    from tresorerie.services import OperationVerrouillee, verifier_verrou
    op = Operation.objects.filter(source_type="paiement", source_id=paiement.pk).select_related("compte").first()
    if not op:
        return None
    if op.rapprochement_id:
        raise ValidationError({"detail": f"Le paiement (reçu {op.numero}) est pointé sur un relevé bancaire : annulez d'abord le rapprochement."})
    try:
        verifier_verrou(op.date, op.compte, nouveau_compte)
    except OperationVerrouillee as e:
        raise ValidationError({"detail": f"{e} Rouvrez la clôture de caisse pour modifier ce paiement."})
    return op


class PaiementDetail(generics.RetrieveUpdateDestroyAPIView):
    """Consultation, modification (montant, type, mode, caisse) et suppression d'un paiement de scolarité.

    La recette de trésorerie et l'échéancier de l'étudiant sont mis à jour automatiquement ; la modification
    est tracée dans les notes de la recette, la suppression annule la recette (le numéro de reçu reste au journal).
    """
    queryset = Paiement.objects.select_related("etudiant", "filiere", "frais", "frais__classe").all()
    serializer_class = PaiementSerializer
    permission_classes = [_EcritureFinance]

    def perform_update(self, serializer):
        from tresorerie.models import CompteTresorerie
        avant = serializer.instance
        ancien = {"montant": avant.montant_paye, "type": avant.paiement_type, "mode": avant.moyen_paiement}
        montant = serializer.validated_data.get("montant_paye", avant.montant_paye)
        if montant is None or Decimal(montant) <= 0:
            raise ValidationError({"montant_paye": ["Le montant doit être supérieur à 0."]})
        nouveau_compte = serializer.validated_data.get("compte_tresorerie")
        _controler_tresorerie(avant, nouveau_compte if isinstance(nouveau_compte, CompteTresorerie) else None)
        with transaction.atomic():
            p = serializer.save()
            recalculer_echeancier(p.etudiant_id, p.annee_academique_id, p.filiere_id)
            from tresorerie.models import Operation
            op = Operation.objects.filter(source_type="paiement", source_id=p.pk).first()
            if op:
                changements = []
                if Decimal(ancien["montant"]) != Decimal(p.montant_paye):
                    changements.append(f"montant {Decimal(ancien['montant']):,.0f} → {Decimal(p.montant_paye):,.0f}".replace(",", " "))
                if ancien["type"] != p.paiement_type:
                    changements.append(f"type {ancien['type']} → {p.paiement_type}")
                if ancien["mode"] != p.moyen_paiement:
                    changements.append(f"mode {ancien['mode']} → {p.moyen_paiement}")
                motif = str(self.request.data.get("motif") or "").strip()
                trace = (f"Modifié le {timezone.localtime():%d/%m/%Y %H:%M} par {_nom(self.request.user)}"
                         f"{' : ' + ', '.join(changements) if changements else ''}{' — motif : ' + motif if motif else ''}")
                op.notes = f"{op.notes}\n{trace}".strip()
                op.save(update_fields=["notes"])

    def perform_destroy(self, instance):
        _controler_tresorerie(instance)
        motif = str(self.request.data.get("motif") or self.request.query_params.get("motif") or "").strip()
        if not motif:
            raise ValidationError({"motif": ["Indiquez le motif de la suppression."]})
        etudiant_id, annee_id, filiere_id = instance.etudiant_id, instance.annee_academique_id, instance.filiere_id
        with transaction.atomic():
            from tresorerie.services import annuler_source
            annuler_source("paiement", instance.pk, f"Paiement supprimé le {timezone.localtime():%d/%m/%Y} par {_nom(self.request.user)} : {motif}")
            instance.delete()
            recalculer_echeancier(etudiant_id, annee_id, filiere_id)


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

            frais_personnalises = False
            if classe:
                # Frais propres à l'étudiant s'ils ont été personnalisés, sinon ceux de la classe
                fe = frais_etudiant(etudiant, classe)
                montant_du_inscription = fe["inscription"]
                montant_du_formation = fe["formation"]
                frais_personnalises = fe["personnalise"]

            # Calculer les paiements effectués (inclure ceux avec et sans frais)
            paiements = paiements_de_l_annee(Paiement.objects.filter(etudiant=etudiant), year_id)
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
                    "frais_personnalises": frais_personnalises,
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
                fe = frais_etudiant(etudiant, classe)
                total_attendu_inscription += fe["inscription"]
                total_attendu_formation += fe["formation"]

        # Montants recouvrés
        paiements_qs = paiements_de_l_annee(Paiement.objects.all(), year_id)

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
                total_du = frais_etudiant(etudiant, classe)["total"]

            total_paye = paiements_de_l_annee(Paiement.objects.filter(etudiant=etudiant), year_id).aggregate(
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
            total_paye_filiere = paiements_de_l_annee(Paiement.objects.filter(
                etudiant__in=etudiants_filiere
            ), year_id).aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")
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
            fe = frais_etudiant(etudiant, classe)
            montant_du_inscription = fe["inscription"]
            montant_du_formation = fe["formation"]
        
        annee_id = derniere_inscription.annee_academique_ref_id if derniere_inscription else year_id
        paiements = paiements_de_l_annee(Paiement.objects.filter(etudiant=etudiant), annee_id)
        montant_paye_inscription = paiements.filter(paiement_type="INSCRIPTION").aggregate(
            total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
        )["total"]
        montant_paye_formation = paiements.filter(paiement_type="FORMATION").aggregate(
            total=Coalesce(Sum("montant_paye"), Value(0, output_field=DecimalField(max_digits=10, decimal_places=2)))
        )["total"]

        # Échéancier effectif (personnel de l'étudiant, sinon celui de la classe ajusté à ses frais)
        installments = []
        if classe:
            resolved = compute_student_retard(etudiant, classe)
            for inst in resolved["installments"]:
                installments.append({
                    "label": inst["label"],
                    "due_date": inst["due_date"],
                    "amount_due": inst["amount_due"],
                    "amount_paid": inst["amount_paid"],
                    "status": inst["status"],
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


class ClassePaymentScheduleListCreateView(generics.ListCreateAPIView):
    queryset = ClassePaymentSchedule.objects.select_related("classe").prefetch_related("installments").all()
    serializer_class = ClassePaymentScheduleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(classe__annee_academique_id=year_id)
        classe_id = self.request.query_params.get("classe")
        if classe_id:
            queryset = queryset.filter(classe_id=classe_id)
        return queryset


class ClassePaymentScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ClassePaymentSchedule.objects.select_related("classe").prefetch_related("installments").all()
    serializer_class = ClassePaymentScheduleSerializer


class StudentResolvedScheduleView(APIView):
    """Get the resolved schedule (global or personal) for a student with retard status."""

    def get(self, request, etudiant_id):
        try:
            etudiant = Etudiant.objects.get(pk=etudiant_id)
        except Etudiant.DoesNotExist:
            return Response({"error": "Etudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)

        year_id = get_current_academic_year_id()
        from etudiants.models import Inscription
        if year_id:
            inscription = Inscription.objects.filter(
                etudiant=etudiant, annee_academique_ref_id=year_id
            ).select_related("classe").first()
        else:
            inscription = Inscription.objects.filter(
                etudiant=etudiant
            ).select_related("classe").order_by("-date_inscription").first()

        if not inscription or not inscription.classe:
            return Response({
                "source": None,
                "installments": [],
                "total_due": 0,
                "total_paid": 0,
                "is_overdue": False,
                "overdue_amount": 0,
                "overdue_days": 0,
            })

        result = compute_student_retard(etudiant, inscription.classe)
        serializer = ResolvedScheduleSerializer(result)
        return Response(serializer.data)


class StudentScheduleOverrideView(APIView):
    """Create or delete a personal schedule override for a student."""

    def post(self, request, etudiant_id):
        try:
            etudiant = Etudiant.objects.get(pk=etudiant_id)
        except Etudiant.DoesNotExist:
            return Response({"error": "Etudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)

        year_id = get_current_academic_year_id()
        from etudiants.models import Inscription
        if year_id:
            inscription = Inscription.objects.filter(
                etudiant=etudiant, annee_academique_ref_id=year_id
            ).select_related("classe").first()
        else:
            inscription = Inscription.objects.filter(
                etudiant=etudiant
            ).select_related("classe").order_by("-date_inscription").first()

        if not inscription or not inscription.classe:
            return Response({"error": "Aucune inscription/classe trouvee"}, status=status.HTTP_400_BAD_REQUEST)

        classe = inscription.classe
        installments_data = request.data.get("installments", [])
        total_amount = request.data.get("total_amount")

        if not installments_data:
            return Response({"error": "Les tranches sont requises"}, status=status.HTTP_400_BAD_REQUEST)

        if not total_amount:
            total_amount = sum(Decimal(str(i.get("amount_due", 0))) for i in installments_data)

        from .models import StudentPaymentPlan, StudentPaymentInstallment, FraisEtudiant

        try:
            total_amount = Decimal(str(total_amount))
            for item in installments_data:
                if Decimal(str(item.get("amount_due", 0))) <= 0:
                    return Response({"error": "Chaque tranche doit avoir un montant positif."}, status=status.HTTP_400_BAD_REQUEST)
                if not item.get("due_date"):
                    return Response({"error": "Chaque tranche doit avoir une date d'échéance."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"error": "Montants invalides."}, status=status.HTTP_400_BAD_REQUEST)

        # Option : le total de l'échéancier devient les frais de formation de l'étudiant
        if str(request.data.get("appliquer_aux_frais", "")).lower() in ("1", "true", "yes"):
            fe, _ = FraisEtudiant.objects.get_or_create(etudiant=etudiant, classe=classe)
            fe.frais_formation = total_amount
            fe.modifie_par = request.user if request.user.is_authenticated else None
            if not fe.motif:
                fe.motif = "Aligné sur l'échéancier personnel"
            fe.save()

        # Un seul échéancier personnel par étudiant et par classe
        StudentPaymentPlan.objects.filter(etudiant=etudiant, classe=classe).delete()

        plan = StudentPaymentPlan.objects.create(
            etudiant=etudiant,
            filiere=etudiant.filiere,
            classe=classe,
            is_override=True,
            mode="CUSTOM",
            total_amount=total_amount,
            status=StudentPaymentPlan.STATUS_ACTIVE,
        )

        from datetime import date as date_type
        from django.utils.dateparse import parse_date
        for item in installments_data:
            raw_date = item["due_date"]
            due_date = raw_date if isinstance(raw_date, date_type) else parse_date(str(raw_date))
            StudentPaymentInstallment.objects.create(
                plan=plan,
                order=item["order"],
                label=item["label"],
                due_date=due_date,
                amount_due=item["amount_due"],
            )

        # Distribute existing payments to the new plan
        from .models import Paiement
        total_paid = paiements_de_l_annee(Paiement.objects.filter(
            etudiant=etudiant, paiement_type="FORMATION"
        ), classe.annee_academique_id).aggregate(total=Sum("montant_paye"))["total"] or Decimal("0")

        remaining = total_paid
        for inst in plan.installments.all().order_by("due_date", "order"):
            if remaining <= 0:
                break
            applied = min(inst.amount_due, remaining)
            inst.amount_paid = applied
            inst.save()
            remaining -= applied

        result = compute_student_retard(etudiant, classe)
        serializer = ResolvedScheduleSerializer(result)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, etudiant_id):
        try:
            etudiant = Etudiant.objects.get(pk=etudiant_id)
        except Etudiant.DoesNotExist:
            return Response({"error": "Etudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)

        year_id = get_current_academic_year_id()
        from etudiants.models import Inscription
        if year_id:
            inscription = Inscription.objects.filter(
                etudiant=etudiant, annee_academique_ref_id=year_id
            ).select_related("classe").first()
        else:
            inscription = Inscription.objects.filter(
                etudiant=etudiant
            ).select_related("classe").order_by("-date_inscription").first()

        if not inscription or not inscription.classe:
            return Response({"error": "Aucune inscription/classe trouvee"}, status=status.HTTP_400_BAD_REQUEST)

        from .models import StudentPaymentPlan
        deleted_count, _ = StudentPaymentPlan.objects.filter(
            etudiant=etudiant, classe=inscription.classe, is_override=True
        ).delete()

        if deleted_count == 0:
            return Response({"message": "Aucun echeancier personnalise a supprimer"}, status=status.HTTP_404_NOT_FOUND)

        result = compute_student_retard(etudiant, inscription.classe)
        serializer = ResolvedScheduleSerializer(result)
        return Response(serializer.data)



def _inscription_annee(etudiant):
    from etudiants.models import Inscription
    year_id = get_current_academic_year_id()
    qs = Inscription.objects.filter(etudiant=etudiant, classe__isnull=False).select_related("classe")
    if year_id:
        qs = qs.filter(Q(annee_academique_ref_id=year_id) | Q(classe__annee_academique_id=year_id))
    return qs.order_by("-date_inscription", "-id").first()


class FraisEtudiantView(APIView):
    """Frais propres à un étudiant pour l'année sélectionnée (en-tête X-Academic-Year).

    GET    : frais effectifs + frais de la classe + payé / reste par type
    PUT    : {frais_inscription: montant|null, frais_formation: montant|null, motif}
             (null = reprendre le montant de la classe)
    DELETE : revenir aux frais de la classe
    """

    def _context(self, etudiant_id):
        try:
            etudiant = Etudiant.objects.get(pk=etudiant_id)
        except Etudiant.DoesNotExist:
            return None, None, Response({"error": "Etudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)
        inscription = _inscription_annee(etudiant)
        if not inscription:
            return etudiant, None, Response({"error": "Aucune inscription dans une classe pour cette année."}, status=status.HTTP_400_BAD_REQUEST)
        return etudiant, inscription.classe, None

    def _payload(self, etudiant, classe):
        from .models import FraisEtudiant
        fe = frais_etudiant(etudiant, classe)
        paiements = paiements_de_l_annee(Paiement.objects.filter(etudiant=etudiant), classe.annee_academique_id)
        paye_ins = paiements.filter(paiement_type="INSCRIPTION").aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")
        paye_form = paiements.filter(paiement_type="FORMATION").aggregate(t=Sum("montant_paye"))["t"] or Decimal("0")
        perso = FraisEtudiant.objects.filter(etudiant=etudiant, classe=classe).select_related("modifie_par").first()
        return {
            "etudiant_id": etudiant.id,
            "classe_id": classe.id,
            "classe_nom": classe.nom,
            "inscription": {"du": float(fe["inscription"]), "classe": float(fe["classe_inscription"]), "personnalise": fe["personnalise_inscription"],
                            "paye": float(paye_ins), "reste": float(fe["inscription"] - paye_ins)},
            "formation": {"du": float(fe["formation"]), "classe": float(fe["classe_formation"]), "personnalise": fe["personnalise_formation"],
                          "paye": float(paye_form), "reste": float(fe["formation"] - paye_form)},
            "total": float(fe["total"]),
            "personnalise": fe["personnalise"],
            "motif": fe["motif"],
            "modifie_le": perso.updated_at if perso else None,
            "modifie_par": f"{perso.modifie_par.noms} {perso.modifie_par.prenoms}".strip() if perso and perso.modifie_par else "",
        }

    def get(self, request, etudiant_id):
        etudiant, classe, err = self._context(etudiant_id)
        if err:
            return err
        return Response(self._payload(etudiant, classe))

    def put(self, request, etudiant_id):
        from .models import FraisEtudiant
        etudiant, classe, err = self._context(etudiant_id)
        if err:
            return err

        def montant(key):
            v = request.data.get(key)
            if v in (None, ""):
                return None
            try:
                d = Decimal(str(v))
            except Exception:
                raise ValueError(key)
            if d < 0:
                raise ValueError(key)
            return d

        try:
            ins = montant("frais_inscription")
            form = montant("frais_formation")
        except ValueError as e:
            return Response({str(e): ["Montant invalide."]}, status=status.HTTP_400_BAD_REQUEST)

        if ins is None and form is None:
            FraisEtudiant.objects.filter(etudiant=etudiant, classe=classe).delete()
        else:
            fe, _ = FraisEtudiant.objects.get_or_create(etudiant=etudiant, classe=classe)
            fe.frais_inscription = ins
            fe.frais_formation = form
            fe.motif = str(request.data.get("motif") or "")[:2000]
            fe.modifie_par = request.user if request.user.is_authenticated else None
            fe.save()
        return Response(self._payload(etudiant, classe))

    def delete(self, request, etudiant_id):
        from .models import FraisEtudiant
        etudiant, classe, err = self._context(etudiant_id)
        if err:
            return err
        FraisEtudiant.objects.filter(etudiant=etudiant, classe=classe).delete()
        return Response(self._payload(etudiant, classe))

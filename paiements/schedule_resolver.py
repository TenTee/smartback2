from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone

ZERO = Decimal("0")


def get_resolved_schedule(etudiant, classe):
    """
    Échéancier effectif d'un étudiant dans une classe.
    Priorité : échéancier personnel de l'étudiant > échéancier global de la classe.

    Returns:
        tuple: (source, schedule_obj, installments_queryset_or_list)
        source: "personal" | "global" | None
    """
    from .models import StudentPaymentPlan, ClassePaymentSchedule

    personal_plan = StudentPaymentPlan.objects.filter(
        etudiant=etudiant,
        classe=classe,
        is_override=True,
    ).exclude(status=StudentPaymentPlan.STATUS_CANCELLED).prefetch_related("installments").first()

    if personal_plan:
        return ("personal", personal_plan, personal_plan.installments.all().order_by("due_date", "order"))

    try:
        global_schedule = classe.payment_schedule
        return ("global", global_schedule, global_schedule.installments.all().order_by("due_date", "order"))
    except ClassePaymentSchedule.DoesNotExist:
        pass

    return (None, None, [])


def _ajuster(montants, total_cible):
    """Répartit `total_cible` proportionnellement aux montants de l'échéancier de la classe."""
    total = sum(montants, ZERO)
    if total <= 0 or not montants:
        return montants
    res = [(m * total_cible / total).quantize(Decimal("1"), rounding=ROUND_HALF_UP) for m in montants]
    res[-1] += total_cible - sum(res, ZERO)
    return res


def compute_student_retard(etudiant, classe, reference_date=None):
    """
    État détaillé des paiements de formation d'un étudiant par rapport à son échéancier effectif.

    Les paiements de formation de l'année sont imputés dans l'ordre des échéances (personnel
    ou global). Si l'étudiant a des frais de formation personnalisés et pas d'échéancier
    personnel, l'échéancier de la classe est ajusté proportionnellement à ses frais.
    """
    from .models import Paiement, StudentPaymentInstallment, paiements_de_l_annee
    from .frais_etudiant import frais_etudiant

    reference_date = reference_date or timezone.localdate()
    frais = frais_etudiant(etudiant, classe)
    source, schedule_obj, raw_installments = get_resolved_schedule(etudiant, classe)
    raw_installments = list(raw_installments)

    total_paid = paiements_de_l_annee(
        Paiement.objects.filter(etudiant=etudiant, paiement_type="FORMATION"),
        classe.annee_academique_id,
    ).aggregate(total=Sum("montant_paye"))["total"] or ZERO

    base = {
        "frais": {k: (float(v) if isinstance(v, Decimal) else v) for k, v in frais.items() if k != "modifie_le"},
        "total_attendu": frais["formation"],
    }
    if source is None:
        return {
            "source": None, "installments": [], "total_due": frais["formation"], "total_paid": total_paid,
            "is_overdue": False, "overdue_amount": ZERO, "overdue_days": 0, "ajuste": False, **base,
        }

    montants = [Decimal(i.amount_due) for i in raw_installments]
    ajuste = False
    if source == "global" and frais["personnalise_formation"] and sum(montants, ZERO) != frais["formation"]:
        montants = _ajuster(montants, frais["formation"])
        ajuste = True

    remaining = Decimal(total_paid)
    result, total_due, overdue_amount, max_overdue_days = [], ZERO, ZERO, 0
    for inst, amount_due in zip(raw_installments, montants):
        total_due += amount_due
        applied = max(ZERO, min(amount_due, remaining))
        remaining -= applied
        balance = amount_due - applied
        if applied >= amount_due:
            status = "PAID"
        elif applied > 0:
            status = "OVERDUE" if inst.due_date < reference_date else "PARTIAL"
        else:
            status = "OVERDUE" if inst.due_date < reference_date else "PENDING"
        days_overdue = 0
        if status == "OVERDUE":
            days_overdue = (reference_date - inst.due_date).days
            overdue_amount += balance
            max_overdue_days = max(max_overdue_days, days_overdue)

        if source == "personal" and (Decimal(inst.amount_paid or 0) != applied or inst.status != status):
            # Garde les tranches personnelles synchronisées avec les paiements réels
            StudentPaymentInstallment.objects.filter(pk=inst.pk).update(amount_paid=applied, status=status)

        result.append({
            "order": inst.order,
            "label": inst.label,
            "due_date": inst.due_date,
            "amount_due": amount_due,
            "amount_paid": applied,
            "balance_due": balance,
            "status": status,
            "days_overdue": days_overdue,
        })

    return {
        "source": source,
        "installments": result,
        "total_due": total_due,
        "total_paid": total_paid,
        "is_overdue": overdue_amount > 0,
        "overdue_amount": overdue_amount,
        "overdue_days": max_overdue_days,
        "ajuste": ajuste,
        **base,
    }

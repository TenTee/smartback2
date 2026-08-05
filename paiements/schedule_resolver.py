from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone


def get_resolved_schedule(etudiant, classe):
    """
    Returns the effective schedule for a student in a class.
    Priority: personal override > global class schedule.

    Returns:
        tuple: (source, schedule_obj, installments_queryset_or_list)
        source: "personal" | "global" | None
    """
    from .models import StudentPaymentPlan, ClassePaymentSchedule

    personal_plan = StudentPaymentPlan.objects.filter(
        etudiant=etudiant,
        classe=classe,
        is_override=True,
        status=StudentPaymentPlan.STATUS_ACTIVE,
    ).prefetch_related("installments").first()

    if personal_plan:
        return ("personal", personal_plan, personal_plan.installments.all())

    try:
        global_schedule = classe.payment_schedule
        return ("global", global_schedule, global_schedule.installments.all())
    except ClassePaymentSchedule.DoesNotExist:
        pass

    return (None, None, [])


def compute_student_retard(etudiant, classe, reference_date=None):
    """
    Computes detailed payment status for a student against their effective schedule.

    Returns dict with:
        source: "personal" | "global" | None
        installments: list of dicts with label, due_date, amount_due, amount_paid, balance_due, status
        total_due: Decimal
        total_paid: Decimal
        is_overdue: bool
        overdue_amount: Decimal
        overdue_days: int (max days overdue across all tranches)
    """
    from .models import Paiement, StudentPaymentInstallment

    reference_date = reference_date or timezone.localdate()
    source, schedule_obj, raw_installments = get_resolved_schedule(etudiant, classe)

    if source is None:
        return {
            "source": None,
            "installments": [],
            "total_due": Decimal("0"),
            "total_paid": Decimal("0"),
            "is_overdue": False,
            "overdue_amount": Decimal("0"),
            "overdue_days": 0,
        }

    if source == "personal":
        result_installments = []
        total_due = Decimal("0")
        total_paid_plan = Decimal("0")
        overdue_amount = Decimal("0")
        max_overdue_days = 0

        for inst in raw_installments:
            inst.refresh_status(reference_date)
            balance = inst.balance_due
            total_due += inst.amount_due
            total_paid_plan += Decimal(inst.amount_paid or 0)

            days_overdue = 0
            if inst.status == StudentPaymentInstallment.STATUS_OVERDUE:
                days_overdue = (reference_date - inst.due_date).days
                overdue_amount += balance
                max_overdue_days = max(max_overdue_days, days_overdue)

            result_installments.append({
                "order": inst.order,
                "label": inst.label,
                "due_date": inst.due_date,
                "amount_due": inst.amount_due,
                "amount_paid": inst.amount_paid,
                "balance_due": balance,
                "status": inst.status,
                "days_overdue": days_overdue,
            })

        return {
            "source": "personal",
            "installments": result_installments,
            "total_due": total_due,
            "total_paid": total_paid_plan,
            "is_overdue": overdue_amount > 0,
            "overdue_amount": overdue_amount,
            "overdue_days": max_overdue_days,
        }

    # source == "global"
    total_paid = Paiement.objects.filter(
        etudiant=etudiant,
        paiement_type="FORMATION",
    ).aggregate(total=Sum("montant_paye"))["total"] or Decimal("0")

    remaining_payment = total_paid
    result_installments = []
    total_due = Decimal("0")
    overdue_amount = Decimal("0")
    max_overdue_days = 0

    for inst in raw_installments:
        amount_due = Decimal(inst.amount_due)
        total_due += amount_due
        applied = min(amount_due, remaining_payment)
        remaining_payment -= applied
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

        result_installments.append({
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
        "source": "global",
        "installments": result_installments,
        "total_due": total_due,
        "total_paid": total_paid,
        "is_overdue": overdue_amount > 0,
        "overdue_amount": overdue_amount,
        "overdue_days": max_overdue_days,
    }

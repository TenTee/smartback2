import calendar
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from etudiants.models import Etudiant
from academique.models import Filiere


class Frais(models.Model):
    classe = models.ForeignKey(
        "academique.Classe",
        on_delete=models.CASCADE,
        related_name="frais",
    )
    libelle = models.CharField(max_length=150)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    obligatoire = models.BooleanField(default=True)
    date_echeance = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["classe", "libelle"], name="unique_frais_per_class_label"),
        ]
        ordering = ["classe__nom", "libelle"]

    def __str__(self):
        return f"{self.libelle} - {self.classe.nom}"


class FilierePaymentPolicy(models.Model):
    MODE_FOUR_INSTALLMENTS = "FOUR_INSTALLMENTS"
    MODE_MONTHLY = "MONTHLY"

    filiere = models.OneToOneField(
        Filiere,
        on_delete=models.CASCADE,
        related_name="payment_policy",
    )
    four_installments_enabled = models.BooleanField(default=False)
    monthly_enabled = models.BooleanField(default=False)
    monthly_start_date = models.DateField(null=True, blank=True)
    monthly_due_day = models.PositiveSmallIntegerField(default=28)
    monthly_installments_count = models.PositiveSmallIntegerField(default=4)
    alert_days_before = models.PositiveSmallIntegerField(default=3)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if not self.four_installments_enabled and not self.monthly_enabled:
            raise ValidationError("Activez au moins un mode de paiement pour la filière.")
        if self.monthly_enabled:
            if not self.monthly_start_date:
                raise ValidationError({"monthly_start_date": "La date de début mensuelle est requise."})
            if not 1 <= self.monthly_due_day <= 31:
                raise ValidationError({"monthly_due_day": "Le jour d'échéance doit être entre 1 et 31."})
            if self.monthly_installments_count < 1:
                raise ValidationError({"monthly_installments_count": "Le nombre d'échéances mensuelles doit être positif."})

    def __str__(self):
        return f"Échéancier - {self.filiere.nom}"

    def get_monthly_schedule(self, total_amount, start_date=None, due_day=None):
        total_amount = Decimal(total_amount or 0)
        count = int(self.monthly_installments_count or 0)
        schedule_start = start_date or self.monthly_start_date
        schedule_due_day = due_day or self.monthly_due_day
        if count < 1 or not schedule_start:
            return []

        amounts = split_amount(total_amount, count)
        return [
            {
                "order": index + 1,
                "label": f"Mensualité {index + 1}",
                "due_date": add_months_with_day(schedule_start, index, schedule_due_day),
                "amount_due": amounts[index],
            }
            for index in range(count)
        ]


class FiliereInstallmentTemplate(models.Model):
    policy = models.ForeignKey(
        FilierePaymentPolicy,
        on_delete=models.CASCADE,
        related_name="four_installments",
    )
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=100, blank=True)
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "order"], name="unique_installment_template_order"),
        ]

    def clean(self):
        if self.order < 1 or self.order > 4:
            raise ValidationError({"order": "L'ordre doit être compris entre 1 et 4."})

    def __str__(self):
        return f"{self.policy.filiere.nom} - Tranche {self.order}"


class ClassePaymentSchedule(models.Model):
    """Global payment schedule for a class - applies to all students unless overridden."""
    classe = models.OneToOneField(
        "academique.Classe",
        on_delete=models.CASCADE,
        related_name="payment_schedule",
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    alert_days_before = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["classe__nom"]

    def __str__(self):
        return f"Echeancier global - {self.classe.nom}"


class ClassePaymentInstallment(models.Model):
    """Individual installment row in a class's global schedule."""
    schedule = models.ForeignKey(
        ClassePaymentSchedule,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=150)
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "order"],
                name="unique_classe_installment_order",
            ),
        ]

    def __str__(self):
        return f"{self.schedule.classe.nom} - {self.label}"


class StudentPaymentPlan(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Actif"),
        (STATUS_COMPLETED, "Terminé"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    MODE_CUSTOM = "CUSTOM"
    MODE_CHOICES = [
        (FilierePaymentPolicy.MODE_FOUR_INSTALLMENTS, "04 tranches"),
        (FilierePaymentPolicy.MODE_MONTHLY, "Mensuel"),
        (MODE_CUSTOM, "Personnalisé"),
    ]

    etudiant = models.ForeignKey(
        Etudiant,
        on_delete=models.CASCADE,
        related_name="payment_plans",
    )
    filiere = models.ForeignKey(
        Filiere,
        on_delete=models.CASCADE,
        related_name="student_payment_plans",
    )
    policy = models.ForeignKey(
        FilierePaymentPolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_plans",
    )
    classe = models.ForeignKey(
        "academique.Classe",
        on_delete=models.CASCADE,
        related_name="student_payment_plans",
        null=True,
        blank=True,
    )
    is_override = models.BooleanField(default=True)
    mode = models.CharField(max_length=30, choices=MODE_CHOICES)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    monthly_start_date = models.DateField(null=True, blank=True)
    monthly_due_day = models.PositiveSmallIntegerField(null=True, blank=True)
    alert_days_before = models.PositiveSmallIntegerField(default=3)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["etudiant", "filiere"], name="unique_student_plan_per_filiere"),
        ]
        ordering = ["-updated_at"]

    def clean(self):
        if self.etudiant_id and self.filiere_id and self.etudiant.filiere_id != self.filiere_id:
            raise ValidationError({"filiere": "Le plan doit correspondre à la filière de l'étudiant."})
        if self.mode == FilierePaymentPolicy.MODE_MONTHLY:
            start_date = self.monthly_start_date or getattr(self.policy, "monthly_start_date", None)
            due_day = self.monthly_due_day or getattr(self.policy, "monthly_due_day", None)
            if not start_date:
                raise ValidationError({"monthly_start_date": "La date de début mensuelle est requise."})
            if not due_day or not 1 <= due_day <= 31:
                raise ValidationError({"monthly_due_day": "Le jour d'échéance mensuelle doit être entre 1 et 31."})

    def __str__(self):
        return f"Plan {self.etudiant.nom} - {self.filiere.nom}"

    def generate_installments(self):
        self.installments.all().delete()
        new_installments = []

        if self.mode == FilierePaymentPolicy.MODE_FOUR_INSTALLMENTS:
            if not self.policy or not self.policy.four_installments_enabled:
                raise ValidationError({"mode": "Le mode 04 tranches n'est pas configuré pour cette filière."})
            templates = list(self.policy.four_installments.all())
            if len(templates) != 4:
                raise ValidationError({"mode": "Configurez les 4 tranches de la filière avant d'assigner ce mode."})
            for template in templates:
                new_installments.append(
                    StudentPaymentInstallment(
                        plan=self,
                        order=template.order,
                        label=template.label or f"Tranche {template.order}",
                        due_date=template.due_date,
                        amount_due=template.amount_due,
                    )
                )
        else:
            if not self.policy or not self.policy.monthly_enabled:
                raise ValidationError({"mode": "Le mode mensuel n'est pas configuré pour cette filière."})
            schedule = self.policy.get_monthly_schedule(
                self.total_amount,
                start_date=self.monthly_start_date,
                due_day=self.monthly_due_day,
            )
            for item in schedule:
                new_installments.append(
                    StudentPaymentInstallment(
                        plan=self,
                        order=item["order"],
                        label=item["label"],
                        due_date=item["due_date"],
                        amount_due=item["amount_due"],
                    )
                )

        for installment in new_installments:
            installment.refresh_status()
        StudentPaymentInstallment.objects.bulk_create(new_installments)
        return new_installments


class StudentPaymentInstallment(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_PAID = "PAID"
    STATUS_OVERDUE = "OVERDUE"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_PARTIAL, "Partiellement payée"),
        (STATUS_PAID, "Payée"),
        (STATUS_OVERDUE, "En retard"),
    ]

    plan = models.ForeignKey(
        StudentPaymentPlan,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=100)
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    last_alert_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "order"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "order"], name="unique_student_installment_order"),
        ]

    def __str__(self):
        return f"{self.plan.etudiant.nom} - {self.label}"

    @property
    def balance_due(self):
        return max(Decimal(self.amount_due or 0) - Decimal(self.amount_paid or 0), Decimal("0"))

    def refresh_status(self, reference_date=None):
        reference_date = reference_date or timezone.localdate()
        if Decimal(self.amount_paid or 0) >= Decimal(self.amount_due or 0):
            self.status = self.STATUS_PAID
        elif Decimal(self.amount_paid or 0) > 0:
            self.status = self.STATUS_OVERDUE if self.due_date < reference_date else self.STATUS_PARTIAL
        else:
            self.status = self.STATUS_OVERDUE if self.due_date < reference_date else self.STATUS_PENDING

    def save(self, *args, **kwargs):
        self.refresh_status()
        super().save(*args, **kwargs)


class Paiement(models.Model):
    etudiant = models.ForeignKey(
        Etudiant,
        on_delete=models.CASCADE,
        related_name="paiements",
        null=True,
    )
    filiere = models.ForeignKey(
        Filiere,
        on_delete=models.CASCADE,
        related_name="paiements",
        editable=False,
    )
    frais = models.ForeignKey(
        Frais,
        on_delete=models.SET_NULL,
        related_name="paiements",
        null=True,
        blank=True,
    )

    TYPE_CHOICES = [
        ("FORMATION", "Frais de formation"),
        ("INSCRIPTION", "Frais d'inscription"),
    ]
    paiement_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="FORMATION",
        help_text="Type de paiement pour distinguer frais de formation et frais d'inscription",
    )
    montant_du = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        null=True,
        blank=True,
    )
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    solde_restant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        editable=False,
    )

    MOYENS = [
        ("cash", "Cash"),
        ("mobile_money", "Mobile Money"),
        ("orange_money", "Orange Money"),
        ("virement", "Virement bancaire"),
        ("cheque", "Chèque"),
    ]
    moyen_paiement = models.CharField(
        max_length=50,
        choices=MOYENS,
        null=True,
        blank=True,
    )

    justificatif = models.FileField(
        upload_to="paiements/justificatifs/",
        null=True,
        blank=True,
        help_text="Importer une photo ou un PDF comme preuve du paiement",
    )
    date_paiement = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if self.etudiant and self.etudiant.filiere:
            self.filiere = self.etudiant.filiere

        reference_amount = Decimal("0")
        if self.frais_id:
            reference_amount = self.frais.montant
        elif self.etudiant_id:
            # Calculer le montant de référence via la classe de l'inscription
            from etudiants.models import Inscription
            inscription = Inscription.objects.filter(
                etudiant=self.etudiant
            ).select_related("classe").order_by("-date_inscription").first()
            if inscription and inscription.classe:
                frais_qs = Frais.objects.filter(classe=inscription.classe)
                if self.paiement_type == "INSCRIPTION":
                    frais_qs = frais_qs.filter(libelle__icontains="inscription")
                else:
                    frais_qs = frais_qs.exclude(libelle__icontains="inscription")
                reference_amount = frais_qs.aggregate(
                    total=models.Sum("montant")
                )["total"] or Decimal("0")

        existing_payments = Paiement.objects.filter(etudiant=self.etudiant)
        if self.frais_id:
            existing_payments = existing_payments.filter(frais=self.frais)
        else:
            existing_payments = existing_payments.filter(paiement_type=self.paiement_type)

        first_payment = not existing_payments.exclude(pk=self.pk).exists()
        self.montant_du = reference_amount if first_payment else None

        total_paid = existing_payments.exclude(pk=self.pk).aggregate(models.Sum("montant_paye"))["montant_paye__sum"] or Decimal("0")
        total_paid += self.montant_paye

        first = existing_payments.exclude(pk=self.pk).order_by("date_paiement").first()
        if first and first.montant_du:
            self.solde_restant = first.montant_du - total_paid
        else:
            self.solde_restant = reference_amount - total_paid

        super().save(*args, **kwargs)

        if is_new and self.paiement_type == "FORMATION":
            self.apply_to_payment_plan()

    def __str__(self):
        return f"{self.etudiant.nom} - {self.filiere.nom}"

    def apply_to_payment_plan(self):
        if not self.etudiant_id or not self.filiere_id:
            return

        plan = StudentPaymentPlan.objects.filter(
            etudiant_id=self.etudiant_id,
            filiere_id=self.filiere_id,
            status=StudentPaymentPlan.STATUS_ACTIVE,
        ).first()
        if not plan:
            return

        remaining = Decimal(self.montant_paye or 0)
        installments = plan.installments.exclude(status=StudentPaymentInstallment.STATUS_PAID).order_by("due_date", "order")
        for installment in installments:
            if remaining <= 0:
                break
            balance = installment.balance_due
            if balance <= 0:
                continue
            applied = min(balance, remaining)
            installment.amount_paid = Decimal(installment.amount_paid or 0) + applied
            installment.save(update_fields=["amount_paid", "status", "updated_at"])
            remaining -= applied

        if not plan.installments.exclude(status=StudentPaymentInstallment.STATUS_PAID).exists():
            plan.status = StudentPaymentPlan.STATUS_COMPLETED
            plan.save(update_fields=["status", "updated_at"])


def split_amount(total_amount, count):
    if count <= 0:
        return []
    total_amount = Decimal(total_amount or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base = (total_amount / count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amounts = [base for _ in range(count)]
    diff = total_amount - sum(amounts)
    amounts[-1] += diff
    return amounts


def add_months_with_day(start_date, offset, desired_day):
    # check if start_date is None
    if start_date is None:
        return None
    month_index = (start_date.month - 1) + offset
    year = start_date.year + (month_index // 12)
    month = (month_index % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(desired_day, last_day)
    return start_date.replace(year=year, month=month, day=day)

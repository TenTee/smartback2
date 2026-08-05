from decimal import Decimal
from rest_framework import serializers

from .models import (
    ClassePaymentInstallment,
    ClassePaymentSchedule,
    FiliereInstallmentTemplate,
    FilierePaymentPolicy,
    Paiement,
    StudentPaymentInstallment,
    StudentPaymentPlan,
)


class FiliereInstallmentTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiliereInstallmentTemplate
        fields = ["id", "order", "label", "due_date", "amount_due"]


class FilierePaymentPolicySerializer(serializers.ModelSerializer):
    four_installments = FiliereInstallmentTemplateSerializer(many=True, required=False)
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)

    class Meta:
        model = FilierePaymentPolicy
        fields = [
            "id",
            "filiere",
            "filiere_nom",
            "four_installments_enabled",
            "monthly_enabled",
            "monthly_start_date",
            "monthly_due_day",
            "monthly_installments_count",
            "alert_days_before",
            "four_installments",
            "updated_at",
        ]
        read_only_fields = ["updated_at", "filiere_nom"]

    def validate(self, attrs):
        four_installments = attrs.get("four_installments", self.initial_data.get("four_installments"))
        filiere = attrs.get("filiere") or getattr(self.instance, "filiere", None)
        four_enabled = attrs.get("four_installments_enabled", getattr(self.instance, "four_installments_enabled", False))
        monthly_enabled = attrs.get("monthly_enabled", getattr(self.instance, "monthly_enabled", False))

        if not four_enabled and not monthly_enabled:
            raise serializers.ValidationError("Activez au moins un mode de paiement.")

        if four_enabled:
            entries = four_installments if four_installments is not None else []
            if self.instance and four_installments is None:
                entries = FiliereInstallmentTemplateSerializer(self.instance.four_installments.all(), many=True).data
            if len(entries) != 4:
                raise serializers.ValidationError({"four_installments": "Vous devez renseigner exactement 4 tranches."})
        return attrs

    def create(self, validated_data):
        installments_data = validated_data.pop("four_installments", [])
        policy = FilierePaymentPolicy.objects.create(**validated_data)
        self._save_installments(policy, installments_data)
        return policy

    def update(self, instance, validated_data):
        installments_data = validated_data.pop("four_installments", None)
        instance = super().update(instance, validated_data)
        if installments_data is not None:
            self._save_installments(instance, installments_data)
        return instance

    def _save_installments(self, policy, installments_data):
        policy.four_installments.all().delete()
        templates = []
        for item in installments_data:
            templates.append(
                FiliereInstallmentTemplate(
                    policy=policy,
                    order=item["order"],
                    label=item.get("label", ""),
                    due_date=item["due_date"],
                    amount_due=item["amount_due"],
                )
            )
        FiliereInstallmentTemplate.objects.bulk_create(templates)


class StudentPaymentInstallmentSerializer(serializers.ModelSerializer):
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = StudentPaymentInstallment
        fields = [
            "id",
            "order",
            "label",
            "due_date",
            "amount_due",
            "amount_paid",
            "balance_due",
            "status",
            "last_alert_at",
        ]


class StudentPaymentPlanSerializer(serializers.ModelSerializer):
    installments = StudentPaymentInstallmentSerializer(many=True, read_only=True)
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)

    class Meta:
        model = StudentPaymentPlan
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "filiere",
            "filiere_nom",
            "policy",
            "mode",
            "total_amount",
            "monthly_start_date",
            "monthly_due_day",
            "alert_days_before",
            "status",
            "installments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "etudiant_nom", "filiere_nom", "installments"]

    def validate(self, attrs):
        etudiant = attrs.get("etudiant") or getattr(self.instance, "etudiant", None)
        filiere = attrs.get("filiere") or getattr(self.instance, "filiere", None) or (etudiant.filiere if etudiant else None)
        mode = attrs.get("mode", getattr(self.instance, "mode", None))

        if etudiant and not filiere:
            filiere = etudiant.filiere
            attrs["filiere"] = filiere
        if not filiere:
            raise serializers.ValidationError({"filiere": "La filière est requise."})

        policy = attrs.get("policy") or getattr(self.instance, "policy", None) or getattr(filiere, "payment_policy", None)
        if not policy:
            raise serializers.ValidationError({"policy": "Aucune politique d'echeancier n'est configuree pour cette filière."})
        attrs["policy"] = policy

        return attrs

    def create(self, validated_data):
        plan = StudentPaymentPlan.objects.create(**validated_data)
        plan.generate_installments()
        return plan


class PaiementSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    frais_libelle = serializers.CharField(source="frais.libelle", read_only=True)
    classe_nom = serializers.CharField(source="frais.classe.nom", read_only=True)

    class Meta:
        model = Paiement
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "filiere",
            "filiere_nom",
            "frais",
            "frais_libelle",
            "classe_nom",
            "paiement_type",
            "montant_du",
            "montant_paye",
            "solde_restant",
            "moyen_paiement",
            "justificatif",
            "date_paiement",
        ]
        read_only_fields = ["solde_restant", "date_paiement"]


class PaiementAggregatedSerializer(serializers.Serializer):
    etudiant = serializers.IntegerField()
    etudiant_nom = serializers.CharField()
    formation = serializers.IntegerField()
    formation_nom = serializers.CharField()
    montant_du = serializers.DecimalField(max_digits=10, decimal_places=2)
    montant_paye_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    solde_restant = serializers.DecimalField(max_digits=10, decimal_places=2)
    montant_du_inscription = serializers.DecimalField(max_digits=10, decimal_places=2)
    montant_paye_inscription_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    solde_restant_inscription = serializers.DecimalField(max_digits=10, decimal_places=2)
    montant_du_formation = serializers.DecimalField(max_digits=10, decimal_places=2)
    montant_paye_formation_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    solde_restant_formation = serializers.DecimalField(max_digits=10, decimal_places=2)
    derniere_date = serializers.DateTimeField(allow_null=True)


class PaymentAlertSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    etudiant_id = serializers.IntegerField()
    etudiant_nom = serializers.CharField()
    formation_id = serializers.IntegerField()
    formation_nom = serializers.CharField()
    installment_id = serializers.IntegerField()
    label = serializers.CharField()
    due_date = serializers.DateField()
    amount_due = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2)
    status = serializers.CharField()
    severity = serializers.CharField()
    message = serializers.CharField()


class ClassePaymentInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassePaymentInstallment
        fields = ["id", "order", "label", "due_date", "amount_due"]


class ClassePaymentScheduleSerializer(serializers.ModelSerializer):
    installments = ClassePaymentInstallmentSerializer(many=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)

    class Meta:
        model = ClassePaymentSchedule
        fields = ["id", "classe", "classe_nom", "total_amount", "alert_days_before", "installments", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def create(self, validated_data):
        installments_data = validated_data.pop("installments", [])
        schedule = ClassePaymentSchedule.objects.create(**validated_data)
        for item in installments_data:
            ClassePaymentInstallment.objects.create(schedule=schedule, **item)
        return schedule

    def update(self, instance, validated_data):
        installments_data = validated_data.pop("installments", None)
        instance = super().update(instance, validated_data)
        if installments_data is not None:
            instance.installments.all().delete()
            for item in installments_data:
                ClassePaymentInstallment.objects.create(schedule=instance, **item)
        return instance


class ResolvedScheduleSerializer(serializers.Serializer):
    source = serializers.CharField(allow_null=True)
    installments = serializers.ListField(child=serializers.DictField())
    total_due = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    is_overdue = serializers.BooleanField()
    overdue_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    overdue_days = serializers.IntegerField()

from decimal import Decimal

from rest_framework import serializers

from .models import (
    FormationInstallmentTemplate,
    FormationPaymentPolicy,
    Paiement,
    StudentPaymentInstallment,
    StudentPaymentPlan,
)


class FormationInstallmentTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormationInstallmentTemplate
        fields = ["id", "order", "label", "due_date", "amount_due"]


class FormationPaymentPolicySerializer(serializers.ModelSerializer):
    four_installments = FormationInstallmentTemplateSerializer(many=True, required=False)
    formation_nom = serializers.CharField(source="formation.intitule", read_only=True)

    class Meta:
        model = FormationPaymentPolicy
        fields = [
            "id",
            "formation",
            "formation_nom",
            "four_installments_enabled",
            "monthly_enabled",
            "monthly_start_date",
            "monthly_due_day",
            "monthly_installments_count",
            "alert_days_before",
            "four_installments",
            "updated_at",
        ]
        read_only_fields = ["updated_at", "formation_nom"]

    def validate(self, attrs):
        four_installments = attrs.get("four_installments", self.initial_data.get("four_installments"))
        formation = attrs.get("formation") or getattr(self.instance, "formation", None)
        four_enabled = attrs.get("four_installments_enabled", getattr(self.instance, "four_installments_enabled", False))
        monthly_enabled = attrs.get("monthly_enabled", getattr(self.instance, "monthly_enabled", False))

        if not four_enabled and not monthly_enabled:
            raise serializers.ValidationError("Activez au moins un mode de paiement.")

        if four_enabled:
            entries = four_installments if four_installments is not None else []
            if self.instance and four_installments is None:
                entries = FormationInstallmentTemplateSerializer(self.instance.four_installments.all(), many=True).data
            if len(entries) != 4:
                raise serializers.ValidationError({"four_installments": "Vous devez renseigner exactement 4 tranches."})
            total = sum(Decimal(str(item.get("amount_due", 0))) for item in entries)
            formation_amount = Decimal(getattr(formation, "montant", 0) or 0)
            if total != formation_amount:
                raise serializers.ValidationError({
                    "four_installments": f"La somme des 4 tranches doit etre egale au montant de la formation ({formation_amount})."
                })

        return attrs

    def create(self, validated_data):
        installments_data = validated_data.pop("four_installments", [])
        policy = FormationPaymentPolicy.objects.create(**validated_data)
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
                FormationInstallmentTemplate(
                    policy=policy,
                    order=item["order"],
                    label=item.get("label", ""),
                    due_date=item["due_date"],
                    amount_due=item["amount_due"],
                )
            )
        FormationInstallmentTemplate.objects.bulk_create(templates)


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
    formation_nom = serializers.CharField(source="formation.intitule", read_only=True)
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    overdue_count = serializers.SerializerMethodField()
    alert_count = serializers.SerializerMethodField()

    class Meta:
        model = StudentPaymentPlan
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "formation",
            "formation_nom",
            "policy",
            "mode",
            "total_amount",
            "monthly_start_date",
            "monthly_due_day",
            "alert_days_before",
            "status",
            "installments",
            "overdue_count",
            "alert_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "etudiant_nom", "formation_nom", "installments", "overdue_count", "alert_count"]

    def validate(self, attrs):
        etudiant = attrs.get("etudiant") or getattr(self.instance, "etudiant", None)
        formation = attrs.get("formation") or getattr(self.instance, "formation", None) or getattr(etudiant, "filiere", None)
        mode = attrs.get("mode", getattr(self.instance, "mode", None))

        if etudiant and not formation:
            formation = etudiant.filiere
            attrs["formation"] = formation
        if not formation:
            raise serializers.ValidationError({"formation": "La formation est requise."})

        policy = attrs.get("policy") or getattr(self.instance, "policy", None) or getattr(formation, "payment_policy", None)
        if not policy:
            raise serializers.ValidationError({"policy": "Aucune politique d'echeancier n'est configuree pour cette formation."})
        attrs["policy"] = policy

        if mode == FormationPaymentPolicy.MODE_FOUR_INSTALLMENTS and not policy.four_installments_enabled:
            raise serializers.ValidationError({"mode": "Le mode 04 tranches n'est pas disponible pour cette formation."})
        if mode == FormationPaymentPolicy.MODE_MONTHLY and not policy.monthly_enabled:
            raise serializers.ValidationError({"mode": "Le mode mensuel n'est pas disponible pour cette formation."})

        if "total_amount" not in attrs:
            attrs["total_amount"] = formation.montant
        if "alert_days_before" not in attrs:
            attrs["alert_days_before"] = policy.alert_days_before
        return attrs

    def create(self, validated_data):
        plan = StudentPaymentPlan.objects.create(**validated_data)
        plan.generate_installments()
        return plan

    def update(self, instance, validated_data):
        regenerate = any(
            field in validated_data
            for field in ["mode", "total_amount", "monthly_start_date", "monthly_due_day", "policy"]
        )
        plan = super().update(instance, validated_data)
        if regenerate:
            plan.generate_installments()
        return plan

    def get_overdue_count(self, obj):
        return obj.installments.filter(status=StudentPaymentInstallment.STATUS_OVERDUE).count()

    def get_alert_count(self, obj):
        return sum(1 for installment in obj.installments.all() if installment.status == StudentPaymentInstallment.STATUS_OVERDUE)


class PaiementSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    formation_nom = serializers.CharField(source="formation.intitule", read_only=True)
    frais_libelle = serializers.CharField(source="frais.libelle", read_only=True)
    classe_nom = serializers.CharField(source="frais.classe.nom", read_only=True)

    class Meta:
        model = Paiement
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "formation",
            "formation_nom",
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

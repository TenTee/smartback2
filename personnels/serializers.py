from rest_framework import serializers
from .models import Personnel

class PersonnelSerializer(serializers.ModelSerializer):
    fonction = serializers.CharField(required=False)
    solde_conges_initial = serializers.IntegerField(read_only=True)
    anciennete_annees = serializers.ReadOnlyField()
    est_eligible_conges = serializers.ReadOnlyField()

    def validate(self, attrs):
        extra_days = attrs.get("jours_conges_supplementaires", 0)
        reason = attrs.get("motif_conges_supplementaires", "")
        if extra_days > 0 and not reason.strip():
            raise serializers.ValidationError({
                "motif_conges_supplementaires": "Le motif est obligatoire pour les congés supplémentaires."
            })
        return attrs

    class Meta:
        model = Personnel
        fields = [
            "id", "nom", "contact", "fonction", "date_inscription", 
            "date_embauche", "solde_conges_initial", "jours_conges_supplementaires",
            "motif_conges_supplementaires", "solde_conges_restant", 
            "salaire", "anciennete_annees", "est_eligible_conges"
        ]

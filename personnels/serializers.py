from rest_framework import serializers
from .models import Personnel

class PersonnelSerializer(serializers.ModelSerializer):
    anciennete_annees = serializers.ReadOnlyField()
    est_eligible_conges = serializers.ReadOnlyField()

    class Meta:
        model = Personnel
        fields = [
            "id", "nom", "contact", "fonction", "date_inscription", 
            "date_embauche", "solde_conges_initial", "solde_conges_restant", 
            "salaire", "anciennete_annees", "est_eligible_conges"
        ]

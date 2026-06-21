# formateurs/serializers.py
from rest_framework import serializers
from .models import Formateur

class FormateurSerializer(serializers.ModelSerializer):
    specialites_nom = serializers.SerializerMethodField()

    class Meta:
        model = Formateur
        fields = [
            'id',
            'nom',
            'email',
            'contact',
            'type_formateur',
            'salaire',
            'taux_horaire',
            'specialites',
            'specialites_nom'
        ]

    def get_specialites_nom(self, obj):
        return [m.nom for m in obj.specialites.all()]
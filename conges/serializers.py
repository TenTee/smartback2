# conges/serializers.py
from rest_framework import serializers
from .models import Conge
from personnels.models import Personnel
from personnels.serializers import PersonnelSerializer

class CongeSerializer(serializers.ModelSerializer):
    personnel_id = serializers.PrimaryKeyRelatedField(
        queryset=Personnel.objects.all(),
        source='personnel',
        write_only=True
    )

    personnel = PersonnelSerializer(read_only=True)

    class Meta:
        model = Conge
        fields = [
            'id',
            'date_debut',
            'date_fin',
            'type_conge',
            'raison',
            'statut',
            'personnel',
            'personnel_id'
        ]

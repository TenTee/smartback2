# formations/serializers.py
from rest_framework import serializers
from .models import Formation, Niveau
from modules.serializers import ModuleSerializer
from paiements.serializers import FormationPaymentPolicySerializer

class NiveauSerializer(serializers.ModelSerializer):
    modules_detail = ModuleSerializer(source="modules", many=True, read_only=True)
    
    class Meta:
        model = Niveau
        fields = ["id", "nom", "modules", "modules_detail"]

class FormationSerializer(serializers.ModelSerializer):
    # Lecture : détails des modules
    modules_detail = ModuleSerializer(source="modules", many=True, read_only=True)
    niveaux_detail = NiveauSerializer(source="niveaux", many=True, read_only=True)
    payment_policy = FormationPaymentPolicySerializer(read_only=True)

    class Meta:
        model = Formation
        fields = [
            "id",
            "intitule",
            "duree_mois",
            "montant",
            "frais_inscription",
            "nombre_niveaux",
            "modules",
            "modules_detail",
            "niveaux_detail",
            "payment_policy",
        ]

    def create(self, validated_data):
        modules = validated_data.pop('modules', [])
        formation = Formation.objects.create(**validated_data)
        formation.modules.set(modules)
        
        # ✅ Auto-création des niveaux
        if formation.nombre_niveaux > 0:
            for i in range(1, formation.nombre_niveaux + 1):
                niveau = Niveau.objects.create(formation=formation, nom=f"Niveau {i}")
                if modules:
                    niveau.modules.set(modules)
        
        return formation

    def update(self, instance, validated_data):
        modules = validated_data.pop('modules', None)
        new_nombre = validated_data.get('nombre_niveaux', instance.nombre_niveaux)
        instance = super().update(instance, validated_data)

        if modules is not None:
            instance.modules.set(modules)

        # ✅ Créer les niveaux manquants si le nombre augmente
        try:
            existing_count = instance.niveaux.count()
            if new_nombre > existing_count:
                start_index = existing_count + 1
                for i in range(start_index, new_nombre + 1):
                    niveau = Niveau.objects.create(formation=instance, nom=f"Niveau {i}")
                    if instance.modules.exists():
                        niveau.modules.set(instance.modules.all())
        except Exception:
            pass

        return instance

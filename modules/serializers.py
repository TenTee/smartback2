from rest_framework import serializers
from .models import Module
from formations.models import Formation

class ModuleSerializer(serializers.ModelSerializer):
    formation = serializers.PrimaryKeyRelatedField(
        queryset=Formation.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    formation_details = serializers.SerializerMethodField()
    formateurs = serializers.SerializerMethodField()
    formations = serializers.SerializerMethodField()  # ✅ ajout

    class Meta:
        model = Module
        fields = [
            'id', 'nom', 'duree', 'coefficient',
            'has_tp', 'pourcentage_cc', 'pourcentage_sn', 'pourcentage_tp',
            'semestre',
            'formation', 'formation_details',
            'formateurs', 'formations'
        ]

    def get_formateurs(self, obj):
        return [
            {
                "id": f.id,
                "nom": f.nom,
                "email": f.email,
                "contact": f.contact
            }
            for f in obj.formateurs.all()
        ]

    def get_formations(self, obj):
        return [
            {
                "id": formation.id,
                "intitule": formation.intitule
            }
            for formation in obj.formations.all()
        ]

    def get_formation_details(self, obj):
        formation = obj.formations.first()
        if not formation:
            return None
        return {
            "id": formation.id,
            "intitule": formation.intitule,
        }

    def create(self, validated_data):
        formation = validated_data.pop("formation", None)
        module = Module.objects.create(**validated_data)
        if formation is not None:
            self._sync_formation(module, formation)
        return module

    def update(self, instance, validated_data):
        formation = validated_data.pop("formation", serializers.empty)
        module = super().update(instance, validated_data)
        if formation is serializers.empty:
            return module
        if formation is None:
            self._clear_formations(module)
        else:
            self._sync_formation(module, formation)
        return module

    def _sync_formation(self, module, formation):
        previous_formations = list(module.formations.all())
        for old_formation in previous_formations:
            if old_formation.id != formation.id:
                old_formation.modules.remove(module)
                for niveau in old_formation.niveaux.all():
                    niveau.modules.remove(module)

        formation.modules.add(module)
        for niveau in formation.niveaux.all():
            niveau.modules.add(module)

    def _clear_formations(self, module):
        previous_formations = list(module.formations.all())
        for formation in previous_formations:
            formation.modules.remove(module)
            for niveau in formation.niveaux.all():
                niveau.modules.remove(module)

    def validate(self, attrs):
        has_tp = attrs.get("has_tp", getattr(self.instance, "has_tp", False))
        p_cc = attrs.get("pourcentage_cc", getattr(self.instance, "pourcentage_cc", 0)) or 0
        p_sn = attrs.get("pourcentage_sn", getattr(self.instance, "pourcentage_sn", 0)) or 0
        p_tp = attrs.get("pourcentage_tp", getattr(self.instance, "pourcentage_tp", 0)) or 0

        if has_tp:
            if p_cc + p_sn + p_tp != 100:
                raise serializers.ValidationError("La somme CC+SN+TP doit être 100%.")
        else:
            if p_cc + p_sn != 100:
                raise serializers.ValidationError("La somme CC+SN doit être 100%.")
            attrs["pourcentage_tp"] = 0
        for key, val in [("pourcentage_cc", p_cc), ("pourcentage_sn", p_sn), ("pourcentage_tp", p_tp)]:
            if val < 0 or val > 100:
                raise serializers.ValidationError(f"{key} doit être entre 0 et 100.")
        return attrs

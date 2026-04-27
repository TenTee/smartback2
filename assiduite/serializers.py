from rest_framework import serializers
from .models import AssiduiteRecord


class AssiduiteRecordSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    filiere_nom = serializers.CharField(source="etudiant.filiere.intitule", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)

    class Meta:
        model = AssiduiteRecord
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "etudiant_matricule",
            "filiere_nom",
            "module",
            "module_nom",
            "date",
            "type",
            "minutes_retard",
            "justifie",
            "justificatif",
            "created_at",
        ]

    def validate(self, attrs):
        type_value = attrs.get("type") or self.instance.type if self.instance else None
        minutes = attrs.get("minutes_retard")
        if type_value == "RETARD":
            if minutes is None:
                raise serializers.ValidationError("minutes_retard est requis pour un retard.")
        if type_value == "ABSENCE":
            attrs["minutes_retard"] = None
        return attrs

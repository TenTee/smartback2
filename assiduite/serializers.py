from rest_framework import serializers
from .models import AssiduiteRecord


class AssiduiteRecordSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    filiere_nom = serializers.CharField(source="etudiant.filiere.intitule", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    parent_nom = serializers.CharField(source="etudiant.nom_parent", read_only=True)
    parent_whatsapp = serializers.CharField(source="etudiant.whatsapp_parent", read_only=True)

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
            "parent_nom",
            "parent_whatsapp",
            "created_at",
        ]

    def validate(self, attrs):
        type_value = attrs.get("type") or (self.instance.type if self.instance else None)
        minutes = attrs.get("minutes_retard")
        justifie = attrs.get("justifie", self.instance.justifie if self.instance else False)
        justificatif = attrs.get("justificatif", self.instance.justificatif if self.instance else None)

        if type_value == "RETARD":
            if minutes is None:
                raise serializers.ValidationError({"minutes_retard": "Les minutes de retard sont requises."})
        if type_value == "ABSENCE":
            attrs["minutes_retard"] = None
        
        if justifie and not justificatif:
            raise serializers.ValidationError({"justificatif": "Un fichier justificatif est obligatoire pour justifier une absence ou un retard."})

        return attrs

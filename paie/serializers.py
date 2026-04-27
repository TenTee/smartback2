from rest_framework import serializers
from .models import Paie

class PaieSerializer(serializers.ModelSerializer):
    beneficiaire_nom = serializers.SerializerMethodField()
    beneficiaire_salaire = serializers.SerializerMethodField()
    beneficiaire_type = serializers.SerializerMethodField()
    justificatif_url = serializers.SerializerMethodField()

    class Meta:
        model = Paie
        fields = [
            "id",
            "beneficiaire_content_type",
            "beneficiaire_object_id",
            "beneficiaire_nom",
            "beneficiaire_salaire",
            "beneficiaire_type",
            "salaire",
            "date",
            "statut",
            "justificatif",       # ✅ champ brut (upload)
            "justificatif_url",
        ]

    def get_beneficiaire_nom(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "nom", None)
        return None

    def get_beneficiaire_salaire(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "salaire", None)
        return None

    def get_beneficiaire_type(self, obj):
        if obj.beneficiaire_content_type:
            return obj.beneficiaire_content_type.model
        return None

    def get_justificatif_url(self, obj):
        request = self.context.get("request")  # ✅ récupère la requête
        if obj.justificatif and hasattr(obj.justificatif, "url"):
            return request.build_absolute_uri(obj.justificatif.url)  # ✅ URL absolue
        return None
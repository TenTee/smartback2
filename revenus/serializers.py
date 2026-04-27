from rest_framework import serializers
from .models import Revenu

class RevenuSerializer(serializers.ModelSerializer):
    justificatif_url = serializers.SerializerMethodField()

    class Meta:
        model = Revenu
        fields = "__all__"  # inclut tous les champs du modèle + justificatif_url

    def get_justificatif_url(self, obj):
        request = self.context.get("request")  # ✅ récupère la requête
        if obj.justificatif and hasattr(obj.justificatif, "url"):
            return request.build_absolute_uri(obj.justificatif.url)  # ✅ URL absolue
        return None
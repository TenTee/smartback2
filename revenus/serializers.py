from rest_framework import serializers
from .models import Revenu

class RevenuSerializer(serializers.ModelSerializer):
    justificatif_url = serializers.SerializerMethodField()

    class Meta:
        model = Revenu
        fields = "__all__"  # inclut tous les champs du modèle + justificatif_url

    def get_justificatif_url(self, obj):
        request = self.context.get("request")
        if obj.justificatif and hasattr(obj.justificatif, "url") and request:
            return request.build_absolute_uri(obj.justificatif.url)
        return None
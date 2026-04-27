# recufactures/serializers.py
from rest_framework import serializers
from .models import Depense

class DepenseSerializer(serializers.ModelSerializer):
    # Champs calculés pour affichage lisible
    responsable_nom = serializers.SerializerMethodField()
    responsable_type = serializers.SerializerMethodField()
    justificatif_url = serializers.SerializerMethodField()  # ✅ champ calculé

    class Meta:
        model = Depense
        fields = '__all__'   # inclut tous les champs du modèle + ceux ajoutés ci-dessous

    def get_responsable_nom(self, obj):
        if obj.responsable and hasattr(obj.responsable, "nom"):
            return obj.responsable.nom
        return None

    def get_responsable_type(self, obj):
        if obj.responsable:
            return obj.responsable._meta.model_name  # "personnel" ou "formateur"
        return None

    def get_justificatif_url(self, obj):
        request = self.context.get("request")  # ✅ récupère la requête
        if obj.justificatif and hasattr(obj.justificatif, "url"):
            return request.build_absolute_uri(obj.justificatif.url)  # ✅ URL absolue
        return None
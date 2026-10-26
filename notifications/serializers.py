from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    categorie_libelle = serializers.CharField(source="get_categorie_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "categorie", "categorie_libelle", "type", "titre", "message", "lien", "niveau", "lu", "lu_le", "cree_le"]

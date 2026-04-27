from rest_framework import serializers
from .models import DemandeArticle
from inventaires.serializers import InventaireSerializer
from django.contrib.contenttypes.models import ContentType

class DemandeSerializer(serializers.ModelSerializer):
    # Article
    article_id = serializers.PrimaryKeyRelatedField(
        queryset=InventaireSerializer.Meta.model.objects.all(),
        source="article",
        write_only=True
    )
    article = InventaireSerializer(read_only=True)

    # Demandeur générique
    demandeur_content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        write_only=True
    )
    demandeur_object_id = serializers.IntegerField(write_only=True)

    # Champ calculé pour afficher le nom du demandeur
    demandeur_nom = serializers.SerializerMethodField()

    class Meta:
        model = DemandeArticle
        fields = [
            "id",
            "reference",        # générée automatiquement
            "article", "article_id",
            "demandeur_content_type", "demandeur_object_id",
            "demandeur_nom",    # affichage lisible
            "date_demande",     # auto-remplie
            "statut",
        ]
        read_only_fields = ["reference", "date_demande"]

    def get_demandeur_nom(self, obj):
        return str(obj.demandeur) if obj.demandeur else None
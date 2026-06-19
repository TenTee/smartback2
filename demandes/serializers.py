from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import DemandeArticle, LigneDemande
from inventaires.serializers import ArticleListSerializer


class LigneDemandeSerializer(serializers.ModelSerializer):
    article_nom = serializers.CharField(source="article.nom", read_only=True)
    article_reference = serializers.CharField(source="article.reference", read_only=True)
    article_categorie = serializers.CharField(source="article.categorie", read_only=True)
    stock_disponible = serializers.IntegerField(source="article.quantite_en_stock", read_only=True)

    class Meta:
        model = LigneDemande
        fields = [
            "id", "article", "article_nom", "article_reference", "article_categorie",
            "quantite_demandee", "quantite_accordee", "notes", "stock_disponible",
        ]


class DemandeSerializer(serializers.ModelSerializer):
    lignes = LigneDemandeSerializer(many=True, read_only=True)
    demandeur_nom = serializers.SerializerMethodField()
    approbateur_nom = serializers.SerializerMethodField()
    statut_display = serializers.CharField(source="get_statut_display", read_only=True)
    priorite_display = serializers.CharField(source="get_priorite_display", read_only=True)
    nb_articles = serializers.SerializerMethodField()

    class Meta:
        model = DemandeArticle
        fields = [
            "id", "reference", "objet", "motif", "priorite", "priorite_display",
            "statut", "statut_display",
            "demandeur_content_type", "demandeur_object_id", "demandeur_nom",
            "approbateur_content_type", "approbateur_object_id", "approbateur_nom",
            "date_demande", "date_traitement", "date_livraison",
            "commentaire_refus", "lignes", "nb_articles",
        ]
        read_only_fields = ["reference", "date_demande"]

    def get_demandeur_nom(self, obj):
        return str(obj.demandeur) if obj.demandeur else None

    def get_approbateur_nom(self, obj):
        return str(obj.approbateur) if obj.approbateur else None

    def get_nb_articles(self, obj):
        return obj.lignes.count()


class DemandeCreateSerializer(serializers.ModelSerializer):
    lignes = LigneDemandeSerializer(many=True)

    class Meta:
        model = DemandeArticle
        fields = [
            "objet", "motif", "priorite",
            "demandeur_content_type", "demandeur_object_id",
            "lignes",
        ]

    def create(self, validated_data):
        lignes_data = validated_data.pop("lignes")
        demande = DemandeArticle.objects.create(**validated_data)
        for ligne in lignes_data:
            LigneDemande.objects.create(demande=demande, **ligne)
        return demande


class DemandeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemandeArticle
        fields = [
            "objet", "motif", "priorite", "statut",
            "commentaire_refus",
            "approbateur_content_type", "approbateur_object_id",
        ]

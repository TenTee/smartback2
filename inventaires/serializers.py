from rest_framework import serializers
from .models import Article, Exemplaire, Mouvement, Inventaire


class ExemplaireSerializer(serializers.ModelSerializer):
    article_nom = serializers.CharField(source="article.nom", read_only=True)
    article_reference = serializers.CharField(source="article.reference", read_only=True)
    attributaire_nom = serializers.SerializerMethodField()
    statut_display = serializers.CharField(source="get_statut_display", read_only=True)
    condition_display = serializers.CharField(source="get_condition_display", read_only=True)

    class Meta:
        model = Exemplaire
        fields = [
            "id", "reference", "article", "article_nom", "article_reference",
            "numero_serie", "statut", "statut_display", "condition", "condition_display",
            "localisation", "notes",
            "attributaire_content_type", "attributaire_object_id", "attributaire_nom",
            "date_attribution", "date_acquisition", "created_at",
        ]
        read_only_fields = ["reference", "created_at"]

    def get_attributaire_nom(self, obj):
        return str(obj.attributaire) if obj.attributaire else None


class ArticleSerializer(serializers.ModelSerializer):
    quantite_en_stock = serializers.IntegerField(read_only=True)
    quantite_en_utilisation = serializers.IntegerField(read_only=True)
    quantite_en_panne = serializers.IntegerField(read_only=True)
    quantite_reforme = serializers.IntegerField(read_only=True)
    stock_bas = serializers.BooleanField(read_only=True)
    exemplaires = ExemplaireSerializer(many=True, read_only=True)

    class Meta:
        model = Article
        fields = [
            "id", "reference", "nom", "description", "categorie",
            "quantite_totale", "seuil_alerte", "prix_unitaire", "fournisseur",
            "quantite_en_stock", "quantite_en_utilisation", "quantite_en_panne",
            "quantite_reforme", "stock_bas", "exemplaires",
            "created_at", "updated_at",
        ]
        read_only_fields = ["reference", "created_at", "updated_at"]


class ArticleListSerializer(serializers.ModelSerializer):
    quantite_en_stock = serializers.IntegerField(read_only=True)
    quantite_en_utilisation = serializers.IntegerField(read_only=True)
    quantite_en_panne = serializers.IntegerField(read_only=True)
    quantite_reforme = serializers.IntegerField(read_only=True)
    stock_bas = serializers.BooleanField(read_only=True)

    class Meta:
        model = Article
        fields = [
            "id", "reference", "nom", "description", "categorie",
            "quantite_totale", "seuil_alerte", "prix_unitaire", "fournisseur",
            "quantite_en_stock", "quantite_en_utilisation", "quantite_en_panne",
            "quantite_reforme", "stock_bas",
            "created_at", "updated_at",
        ]
        read_only_fields = ["reference", "created_at", "updated_at"]


class ArticleCreateSerializer(serializers.ModelSerializer):
    quantite_initiale = serializers.IntegerField(write_only=True, default=0, min_value=0)
    condition = serializers.ChoiceField(
        choices=Exemplaire.CONDITIONS, write_only=True, default="neuf", required=False
    )
    localisation = serializers.CharField(write_only=True, default="", required=False, allow_blank=True)

    class Meta:
        model = Article
        fields = [
            "id", "reference", "nom", "description", "categorie",
            "quantite_totale", "seuil_alerte", "prix_unitaire", "fournisseur",
            "quantite_initiale", "condition", "localisation",
        ]
        read_only_fields = ["reference"]

    def create(self, validated_data):
        quantite_initiale = validated_data.pop("quantite_initiale", 0)
        condition = validated_data.pop("condition", "neuf")
        localisation = validated_data.pop("localisation", "")
        validated_data["quantite_totale"] = quantite_initiale
        article = Article.objects.create(**validated_data)
        for _ in range(quantite_initiale):
            Exemplaire.objects.create(
                article=article,
                statut="en_stock",
                condition=condition,
                localisation=localisation,
            )
        return article


class MouvementSerializer(serializers.ModelSerializer):
    exemplaire_reference = serializers.CharField(source="exemplaire.reference", read_only=True)
    article_nom = serializers.CharField(source="exemplaire.article.nom", read_only=True)
    type_display = serializers.CharField(source="get_type_mouvement_display", read_only=True)
    responsable_nom = serializers.SerializerMethodField()
    destinataire_nom = serializers.SerializerMethodField()

    class Meta:
        model = Mouvement
        fields = [
            "id", "reference", "exemplaire", "exemplaire_reference", "article_nom",
            "type_mouvement", "type_display", "date", "motif",
            "responsable_content_type", "responsable_object_id", "responsable_nom",
            "destinataire_content_type", "destinataire_object_id", "destinataire_nom",
            "localisation_source", "localisation_destination",
        ]
        read_only_fields = ["reference", "date"]

    def get_responsable_nom(self, obj):
        return str(obj.responsable) if obj.responsable else None

    def get_destinataire_nom(self, obj):
        return str(obj.destinataire) if obj.destinataire else None


# Legacy serializer kept for backward compatibility
class InventaireSerializer(serializers.ModelSerializer):
    quantite = serializers.IntegerField(write_only=True, required=False, default=1)

    class Meta:
        model = Inventaire
        fields = '__all__'
        read_only_fields = ['reference']

    def create(self, validated_data):
        quantite = validated_data.pop('quantite', 1)
        articles = []
        for i in range(quantite):
            article = Inventaire.objects.create(**validated_data)
            articles.append(article)
        return articles if quantite > 1 else articles[0]

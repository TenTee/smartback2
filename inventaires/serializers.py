from rest_framework import serializers
from .models import (
    Article, Batiment, CampagneInventaire, Constat, Emplacement, Exemplaire, Intervention, Inventaire, Mouvement,
    MouvementStock, Site,
)


def _nom_user(u):
    if not u:
        return ""
    return f"{getattr(u, 'prenoms', '') or ''} {getattr(u, 'noms', '') or ''}".strip() or u.username


class SiteSerializer(serializers.ModelSerializer):
    nb_batiments = serializers.IntegerField(read_only=True, default=0)
    nb_emplacements = serializers.IntegerField(read_only=True, default=0)
    nb_materiels = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Site
        fields = ["id", "nom", "adresse", "notes", "actif", "nb_batiments", "nb_emplacements", "nb_materiels"]


class BatimentSerializer(serializers.ModelSerializer):
    site_nom = serializers.CharField(source="site.nom", read_only=True)
    nb_emplacements = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Batiment
        fields = ["id", "site", "site_nom", "nom", "code", "actif", "nb_emplacements"]


class EmplacementSerializer(serializers.ModelSerializer):
    site_nom = serializers.CharField(source="site.nom", read_only=True)
    batiment_nom = serializers.CharField(source="batiment.nom", read_only=True, default="")
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    salle_nom = serializers.CharField(source="salle.nom", read_only=True, default="")
    chemin = serializers.CharField(read_only=True)
    nb_materiels = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Emplacement
        fields = ["id", "site", "site_nom", "batiment", "batiment_nom", "nom", "type", "type_libelle", "code", "etage",
                  "salle", "salle_nom", "responsable", "actif", "code_qr", "chemin", "nb_materiels"]
        read_only_fields = ["code_qr"]

    def validate(self, data):
        site = data.get("site") or getattr(self.instance, "site", None)
        bat = data.get("batiment") if "batiment" in data else getattr(self.instance, "batiment", None)
        if bat and site and bat.site_id != site.id:
            raise serializers.ValidationError({"batiment": ["Ce bâtiment n'appartient pas au site choisi."]})
        return data


class ExemplaireSerializer(serializers.ModelSerializer):
    article_nom = serializers.CharField(source="article.nom", read_only=True)
    article_reference = serializers.CharField(source="article.reference", read_only=True)
    attributaire_nom = serializers.SerializerMethodField()
    statut_display = serializers.CharField(source="get_statut_display", read_only=True)
    condition_display = serializers.CharField(source="get_condition_display", read_only=True)
    categorie = serializers.CharField(source="article.categorie", read_only=True)
    marque = serializers.CharField(source="article.marque", read_only=True)
    modele = serializers.CharField(source="article.modele", read_only=True)
    emplacement_chemin = serializers.SerializerMethodField()
    site = serializers.IntegerField(source="emplacement.site_id", read_only=True, default=None)
    valeur_origine = serializers.SerializerMethodField()
    valeur_actuelle = serializers.SerializerMethodField()
    sous_garantie = serializers.BooleanField(read_only=True)
    pannes_ouvertes = serializers.SerializerMethodField()

    class Meta:
        model = Exemplaire
        fields = [
            "id", "reference", "article", "article_nom", "article_reference", "categorie", "marque", "modele",
            "numero_serie", "statut", "statut_display", "condition", "condition_display",
            "localisation", "emplacement", "emplacement_chemin", "site", "notes", "code_qr",
            "attributaire_content_type", "attributaire_object_id", "attributaire_nom",
            "date_attribution", "date_acquisition", "valeur_achat", "valeur_origine", "valeur_actuelle",
            "fournisseur", "numero_facture", "date_fin_garantie", "sous_garantie", "date_reforme", "motif_reforme",
            "pannes_ouvertes", "created_at",
        ]
        read_only_fields = ["reference", "created_at", "code_qr", "statut", "attributaire_content_type", "attributaire_object_id",
                            "date_attribution", "date_reforme", "motif_reforme"]

    def get_attributaire_nom(self, obj):
        try:
            return str(obj.attributaire) if obj.attributaire else None
        except Exception:  # noqa: BLE001  (attributaire supprimé)
            return None

    def get_emplacement_chemin(self, obj):
        return obj.emplacement.chemin if obj.emplacement_id else (obj.localisation or "")

    def get_valeur_origine(self, obj):
        return float(obj.valeur_origine)

    def get_valeur_actuelle(self, obj):
        return float(obj.valeur_actuelle())

    def get_pannes_ouvertes(self, obj):
        n = getattr(obj, "nb_pannes_ouvertes", None)
        if n is not None:
            return n
        return obj.interventions.filter(statut__in=["signalee", "en_cours"]).count()


class ArticleSerializer(serializers.ModelSerializer):
    quantite_en_stock = serializers.IntegerField(read_only=True)
    quantite_en_utilisation = serializers.IntegerField(read_only=True)
    quantite_en_panne = serializers.IntegerField(read_only=True)
    quantite_reforme = serializers.IntegerField(read_only=True)
    stock_bas = serializers.BooleanField(read_only=True)
    annees_amortissement = serializers.IntegerField(read_only=True)
    exemplaires = ExemplaireSerializer(many=True, read_only=True)

    class Meta:
        model = Article
        fields = [
            "id", "reference", "nom", "description", "categorie", "type_article", "marque", "modele", "unite",
            "duree_amortissement", "annees_amortissement", "stock", "photo",
            "quantite_totale", "seuil_alerte", "prix_unitaire", "fournisseur",
            "quantite_en_stock", "quantite_en_utilisation", "quantite_en_panne",
            "quantite_reforme", "stock_bas", "exemplaires",
            "created_at", "updated_at",
        ]
        read_only_fields = ["reference", "created_at", "updated_at", "stock"]


class ArticleListSerializer(serializers.ModelSerializer):
    quantite_en_stock = serializers.IntegerField(read_only=True)
    quantite_en_utilisation = serializers.IntegerField(read_only=True)
    quantite_en_panne = serializers.IntegerField(read_only=True)
    quantite_reforme = serializers.IntegerField(read_only=True)
    stock_bas = serializers.BooleanField(read_only=True)
    annees_amortissement = serializers.IntegerField(read_only=True)

    class Meta:
        model = Article
        fields = [
            "id", "reference", "nom", "description", "categorie", "type_article", "marque", "modele", "unite",
            "duree_amortissement", "annees_amortissement", "stock", "photo",
            "quantite_totale", "seuil_alerte", "prix_unitaire", "fournisseur",
            "quantite_en_stock", "quantite_en_utilisation", "quantite_en_panne",
            "quantite_reforme", "stock_bas",
            "created_at", "updated_at",
        ]
        read_only_fields = ["reference", "created_at", "updated_at", "stock"]


class ArticleCreateSerializer(serializers.ModelSerializer):
    quantite_initiale = serializers.IntegerField(write_only=True, default=0, min_value=0)
    condition = serializers.ChoiceField(
        choices=Exemplaire.CONDITIONS, write_only=True, default="neuf", required=False
    )
    localisation = serializers.CharField(write_only=True, default="", required=False, allow_blank=True)

    class Meta:
        model = Article
        fields = [
            "id", "reference", "nom", "description", "categorie", "type_article", "marque", "modele", "unite",
            "duree_amortissement", "quantite_totale", "seuil_alerte", "prix_unitaire", "fournisseur",
            "quantite_initiale", "condition", "localisation",
        ]
        read_only_fields = ["reference"]

    def create(self, validated_data):
        quantite_initiale = validated_data.pop("quantite_initiale", 0)
        condition = validated_data.pop("condition", "neuf")
        localisation = validated_data.pop("localisation", "")
        validated_data["quantite_totale"] = quantite_initiale
        article = Article.objects.create(**validated_data)
        if article.type_article == "consommable":
            if quantite_initiale:
                MouvementStock.objects.create(article=article, type="entree", quantite=quantite_initiale,
                                              stock_apres=quantite_initiale, motif="Stock initial")
                article.stock = quantite_initiale
                article.quantite_totale = 0
                article.save(update_fields=["stock", "quantite_totale"])
            return article
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
    utilisateur_nom = serializers.SerializerMethodField()

    class Meta:
        model = Mouvement
        fields = [
            "id", "reference", "exemplaire", "exemplaire_reference", "article_nom",
            "type_mouvement", "type_display", "date", "motif",
            "responsable_content_type", "responsable_object_id", "responsable_nom",
            "destinataire_content_type", "destinataire_object_id", "destinataire_nom",
            "localisation_source", "localisation_destination", "emplacement_source", "emplacement_destination",
            "utilisateur_nom",
        ]
        read_only_fields = ["reference", "date"]

    def get_responsable_nom(self, obj):
        try:
            return str(obj.responsable) if obj.responsable else None
        except Exception:  # noqa: BLE001
            return None

    def get_destinataire_nom(self, obj):
        try:
            return str(obj.destinataire) if obj.destinataire else None
        except Exception:  # noqa: BLE001
            return None

    def get_utilisateur_nom(self, obj):
        return _nom_user(obj.utilisateur)


class MouvementStockSerializer(serializers.ModelSerializer):
    article_nom = serializers.CharField(source="article.nom", read_only=True)
    unite = serializers.CharField(source="article.unite", read_only=True)
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    emplacement_chemin = serializers.CharField(source="emplacement.chemin", read_only=True, default="")
    utilisateur_nom = serializers.SerializerMethodField()

    class Meta:
        model = MouvementStock
        fields = ["id", "article", "article_nom", "unite", "type", "type_libelle", "quantite", "stock_apres", "emplacement",
                  "emplacement_chemin", "destinataire", "prix_unitaire", "motif", "date", "utilisateur_nom"]

    def get_utilisateur_nom(self, obj):
        return _nom_user(obj.utilisateur)


class InterventionSerializer(serializers.ModelSerializer):
    exemplaire_reference = serializers.CharField(source="exemplaire.reference", read_only=True)
    article_nom = serializers.CharField(source="exemplaire.article.nom", read_only=True)
    emplacement_chemin = serializers.SerializerMethodField()
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    priorite_libelle = serializers.CharField(source="get_priorite_display", read_only=True)
    signale_par_nom = serializers.SerializerMethodField()
    operation_numero = serializers.CharField(source="operation_tresorerie.numero", read_only=True, default="")

    class Meta:
        model = Intervention
        fields = ["id", "reference", "exemplaire", "exemplaire_reference", "article_nom", "emplacement_chemin", "type",
                  "type_libelle", "statut", "statut_libelle", "priorite", "priorite_libelle", "description", "photo",
                  "signale_par_nom", "signale_le", "technicien", "date_debut", "date_fin", "cout", "resolution",
                  "operation_numero"]
        read_only_fields = ["reference", "statut", "signale_le", "date_fin", "resolution"]

    def get_emplacement_chemin(self, obj):
        e = obj.exemplaire
        return e.emplacement.chemin if e.emplacement_id else e.localisation

    def get_signale_par_nom(self, obj):
        return _nom_user(obj.signale_par)


class CampagneSerializer(serializers.ModelSerializer):
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    cree_par_nom = serializers.SerializerMethodField()
    sites_noms = serializers.SerializerMethodField()
    emplacements_noms = serializers.SerializerMethodField()
    nb_constats = serializers.SerializerMethodField()

    class Meta:
        model = CampagneInventaire
        fields = ["id", "reference", "nom", "statut", "statut_libelle", "sites", "sites_noms", "emplacements", "emplacements_noms",
                  "date_debut", "date_cloture", "commentaire", "cree_par_nom", "resultat", "nb_constats"]
        read_only_fields = ["reference", "statut", "date_debut", "date_cloture", "resultat"]

    def get_cree_par_nom(self, obj):
        return _nom_user(obj.cree_par)

    def get_sites_noms(self, obj):
        return [s.nom for s in obj.sites.all()]

    def get_emplacements_noms(self, obj):
        return [e.chemin for e in obj.emplacements.all()]

    def get_nb_constats(self, obj):
        return obj.constats.count()


class ConstatSerializer(serializers.ModelSerializer):
    exemplaire_reference = serializers.CharField(source="exemplaire.reference", read_only=True)
    article_nom = serializers.CharField(source="exemplaire.article.nom", read_only=True)
    emplacement_chemin = serializers.CharField(source="emplacement.chemin", read_only=True, default="")
    scanne_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = Constat
        fields = ["id", "campagne", "exemplaire", "exemplaire_reference", "article_nom", "emplacement", "emplacement_chemin",
                  "condition", "note", "scanne_par_nom", "date"]

    def get_scanne_par_nom(self, obj):
        return _nom_user(obj.scanne_par)


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

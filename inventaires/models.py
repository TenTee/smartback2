import secrets
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


def code_qr():
    return secrets.token_hex(6)  # 12 caractères, imprévisible : imprimé dans le QR code de l'étiquette


# ---------------------------------------------------------------------------
# Localisation : site → bâtiment → emplacement (salle, bureau, magasin…)
# ---------------------------------------------------------------------------
class Site(models.Model):
    nom = models.CharField(max_length=150, unique=True)
    adresse = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Batiment(models.Model):
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="batiments")
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True, default="")
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["site__nom", "nom"]
        constraints = [models.UniqueConstraint(fields=["site", "nom"], name="unique_batiment_site")]

    def __str__(self):
        return f"{self.site.nom} › {self.nom}"


class Emplacement(models.Model):
    TYPES = [
        ("salle", "Salle de cours"), ("labo", "Laboratoire / salle informatique"), ("bureau", "Bureau"),
        ("magasin", "Magasin / réserve"), ("atelier", "Atelier"), ("commun", "Espace commun"), ("exterieur", "Extérieur"),
        ("autre", "Autre"),
    ]
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="emplacements")
    batiment = models.ForeignKey(Batiment, on_delete=models.PROTECT, null=True, blank=True, related_name="emplacements")
    nom = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=TYPES, default="salle")
    code = models.CharField(max_length=30, blank=True, default="")
    etage = models.CharField(max_length=30, blank=True, default="")
    salle = models.OneToOneField("emploidutemps.Salle", on_delete=models.SET_NULL, null=True, blank=True, related_name="emplacement_inventaire")
    responsable = models.CharField(max_length=150, blank=True, default="", help_text="Personne responsable du matériel du lieu")
    actif = models.BooleanField(default=True)
    code_qr = models.CharField(max_length=32, unique=True, default=code_qr)

    class Meta:
        ordering = ["site__nom", "batiment__nom", "nom"]

    def __str__(self):
        return self.chemin

    @property
    def chemin(self):
        parts = [self.site.nom if self.site_id else "", self.batiment.nom if self.batiment_id else "", self.nom]
        return " › ".join(p for p in parts if p)


class Article(models.Model):
    CATEGORIES = [
        ("Informatique", "Informatique"),
        ("Mobilier", "Mobilier"),
        ("Électronique", "Électronique"),
        ("Papeterie", "Papeterie"),
        ("Fourniture", "Fourniture"),
        ("Équipement", "Équipement"),
        ("Autre", "Autre"),
    ]

    TYPES = [("equipement", "Équipement (suivi à l'unité)"), ("consommable", "Consommable (suivi en quantité)")]
    # Durée d'amortissement par défaut (années) selon la catégorie
    AMORTISSEMENT = {"Informatique": 3, "Électronique": 5, "Mobilier": 10, "Équipement": 5, "Papeterie": 1, "Fourniture": 1, "Autre": 5}

    reference = models.CharField(max_length=30, unique=True, editable=False)
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    categorie = models.CharField(max_length=100, choices=CATEGORIES, default="Autre")
    type_article = models.CharField(max_length=12, choices=TYPES, default="equipement")
    marque = models.CharField(max_length=100, blank=True, default="")
    modele = models.CharField(max_length=100, blank=True, default="")
    unite = models.CharField(max_length=30, blank=True, default="unité", help_text="Consommables : ramette, carton, litre…")
    duree_amortissement = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Années (vide : selon la catégorie)")
    stock = models.IntegerField(default=0, help_text="Consommables : quantité en stock")
    photo = models.ImageField(upload_to="inventaire/articles/", null=True, blank=True)
    quantite_totale = models.PositiveIntegerField(default=0)
    seuil_alerte = models.PositiveIntegerField(default=5)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fournisseur = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.reference = f"ART-{self.pk:04d}"
            super().save(update_fields=["reference"])
        else:
            super().save(*args, **kwargs)

    @property
    def annees_amortissement(self):
        return self.duree_amortissement or self.AMORTISSEMENT.get(self.categorie, 5)

    @property
    def quantite_en_stock(self):
        if self.type_article == "consommable":
            return self.stock
        return self.exemplaires.filter(statut="en_stock").count()

    @property
    def quantite_en_utilisation(self):
        return self.exemplaires.filter(statut="en_utilisation").count()

    @property
    def quantite_en_panne(self):
        return self.exemplaires.filter(statut="en_panne").count()

    @property
    def quantite_reforme(self):
        return self.exemplaires.filter(statut="reforme").count()

    @property
    def stock_bas(self):
        return self.quantite_en_stock <= self.seuil_alerte

    def __str__(self):
        return f"{self.nom} ({self.reference})"

    class Meta:
        ordering = ["-created_at"]


class Exemplaire(models.Model):
    STATUTS = [
        ("en_stock", "En stock"),
        ("en_utilisation", "En utilisation"),
        ("en_panne", "En panne"),
        ("en_maintenance", "En maintenance"),
        ("perdu", "Perdu / introuvable"),
        ("reforme", "Réformé"),
    ]

    CONDITIONS = [
        ("neuf", "Neuf"),
        ("bon", "Bon état"),
        ("usage", "Usagé"),
        ("endommage", "Endommagé"),
    ]

    reference = models.CharField(max_length=30, unique=True, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="exemplaires")
    numero_serie = models.CharField(max_length=100, blank=True, default="")
    statut = models.CharField(max_length=20, choices=STATUTS, default="en_stock")
    condition = models.CharField(max_length=20, choices=CONDITIONS, default="neuf")
    localisation = models.CharField(max_length=200, blank=True, default="")
    emplacement = models.ForeignKey(Emplacement, on_delete=models.SET_NULL, null=True, blank=True, related_name="exemplaires")
    notes = models.TextField(blank=True, default="")
    code_qr = models.CharField(max_length=32, unique=True, null=True, blank=True)
    valeur_achat = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, help_text="Vide : prix unitaire de l'article")
    fournisseur = models.CharField(max_length=200, blank=True, default="")
    numero_facture = models.CharField(max_length=60, blank=True, default="")
    date_fin_garantie = models.DateField(null=True, blank=True)
    date_reforme = models.DateField(null=True, blank=True)
    motif_reforme = models.CharField(max_length=255, blank=True, default="")

    attributaire_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    attributaire_object_id = models.PositiveIntegerField(null=True, blank=True)
    attributaire = GenericForeignKey("attributaire_content_type", "attributaire_object_id")
    date_attribution = models.DateField(null=True, blank=True)

    date_acquisition = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.code_qr:
            self.code_qr = code_qr()
        if self.emplacement_id:
            self.localisation = str(self.emplacement)[:200]
        if not self.pk:
            super().save(*args, **kwargs)
            self.reference = f"EXP-{self.pk:05d}"
            super().save(update_fields=["reference"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.article.nom} - {self.reference}"

    # --- Valeur et amortissement (linéaire)
    @property
    def valeur_origine(self):
        v = self.valeur_achat if self.valeur_achat is not None else self.article.prix_unitaire
        return Decimal(v or 0)

    def valeur_actuelle(self, au=None):
        if self.statut == "reforme":
            return Decimal(0)
        debut = self.date_acquisition or (self.created_at.date() if self.created_at else None)
        if isinstance(debut, str):
            from django.utils.dateparse import parse_date
            debut = parse_date(debut)
        if not debut:
            return self.valeur_origine
        annees = Decimal(self.article.annees_amortissement or 1)
        jours = Decimal(max(0, ((au or date.today()) - debut).days))
        reste = Decimal(1) - jours / (annees * Decimal("365.25"))
        return (self.valeur_origine * max(Decimal(0), reste)).quantize(Decimal("1"))

    @property
    def sous_garantie(self):
        d = self.date_fin_garantie
        if isinstance(d, str):
            from django.utils.dateparse import parse_date
            d = parse_date(d)
        return bool(d and d >= date.today())

    class Meta:
        ordering = ["-created_at"]


class Mouvement(models.Model):
    TYPES = [
        ("entree", "Entrée en stock"),
        ("sortie", "Sortie / Attribution"),
        ("retour", "Retour en stock"),
        ("transfert", "Transfert"),
        ("maintenance", "Envoi en maintenance"),
        ("reforme", "Réforme"),
        ("inventaire", "Constat d'inventaire"),
    ]

    reference = models.CharField(max_length=30, unique=True, editable=False)
    exemplaire = models.ForeignKey(Exemplaire, on_delete=models.CASCADE, related_name="mouvements")
    type_mouvement = models.CharField(max_length=20, choices=TYPES)
    date = models.DateTimeField(auto_now_add=True)
    motif = models.TextField(blank=True, default="")

    responsable_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    responsable_object_id = models.PositiveIntegerField(null=True, blank=True)
    responsable = GenericForeignKey("responsable_content_type", "responsable_object_id")

    destinataire_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mouvements_recus"
    )
    destinataire_object_id = models.PositiveIntegerField(null=True, blank=True)
    destinataire = GenericForeignKey("destinataire_content_type", "destinataire_object_id")

    localisation_source = models.CharField(max_length=200, blank=True, default="")
    localisation_destination = models.CharField(max_length=200, blank=True, default="")
    emplacement_source = models.ForeignKey(Emplacement, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements_sortants")
    emplacement_destination = models.ForeignKey(Emplacement, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements_entrants")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements_inventaire")

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.reference = f"MVT-{self.pk:05d}"
            super().save(update_fields=["reference"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - {self.get_type_mouvement_display()}"

    class Meta:
        ordering = ["-date"]


# ---------------------------------------------------------------------------
# Consommables : mouvements de stock en quantité
# ---------------------------------------------------------------------------
class MouvementStock(models.Model):
    TYPES = [("entree", "Entrée"), ("sortie", "Sortie"), ("ajustement", "Ajustement d'inventaire")]
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="mouvements_stock")
    type = models.CharField(max_length=12, choices=TYPES)
    quantite = models.IntegerField(help_text="Toujours positive ; un ajustement fixe le stock compté")
    stock_apres = models.IntegerField(default=0)
    emplacement = models.ForeignKey(Emplacement, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements_stock")
    destinataire = models.CharField(max_length=200, blank=True, default="")
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    motif = models.CharField(max_length=255, blank=True, default="")
    date = models.DateTimeField(auto_now_add=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="mouvements_stock")

    class Meta:
        ordering = ["-date", "-id"]


# ---------------------------------------------------------------------------
# Pannes & maintenance
# ---------------------------------------------------------------------------
class Intervention(models.Model):
    TYPES = [("panne", "Panne signalée"), ("preventive", "Maintenance préventive"), ("reparation", "Réparation"), ("installation", "Installation / configuration")]
    STATUTS = [("signalee", "Signalée"), ("en_cours", "En cours"), ("resolue", "Résolue"), ("irreparable", "Irréparable"), ("annulee", "Annulée")]
    PRIORITES = [("basse", "Basse"), ("normale", "Normale"), ("haute", "Haute"), ("urgente", "Urgente")]

    reference = models.CharField(max_length=30, unique=True, editable=False)
    exemplaire = models.ForeignKey(Exemplaire, on_delete=models.CASCADE, related_name="interventions")
    type = models.CharField(max_length=15, choices=TYPES, default="panne")
    statut = models.CharField(max_length=12, choices=STATUTS, default="signalee", db_index=True)
    priorite = models.CharField(max_length=10, choices=PRIORITES, default="normale")
    description = models.TextField()
    photo = models.ImageField(upload_to="inventaire/pannes/", null=True, blank=True)
    signale_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="pannes_signalees")
    signale_le = models.DateTimeField(auto_now_add=True)
    technicien = models.CharField(max_length=150, blank=True, default="", help_text="Technicien ou prestataire")
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    cout = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    resolution = models.TextField(blank=True, default="")
    statut_precedent = models.CharField(max_length=20, blank=True, default="")
    operation_tresorerie = models.ForeignKey("tresorerie.Operation", on_delete=models.SET_NULL, null=True, blank=True, related_name="interventions")

    class Meta:
        ordering = ["-signale_le", "-id"]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.reference = f"INT-{self.pk:05d}"
            super().save(update_fields=["reference"])
        else:
            super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Inventaire physique (campagnes de comptage)
# ---------------------------------------------------------------------------
class CampagneInventaire(models.Model):
    STATUTS = [("en_cours", "En cours"), ("cloturee", "Clôturée")]
    reference = models.CharField(max_length=30, unique=True, editable=False)
    nom = models.CharField(max_length=150)
    statut = models.CharField(max_length=10, choices=STATUTS, default="en_cours")
    sites = models.ManyToManyField(Site, blank=True, related_name="campagnes")
    emplacements = models.ManyToManyField(Emplacement, blank=True, related_name="campagnes", help_text="Vide : tous les emplacements des sites choisis")
    date_debut = models.DateField(auto_now_add=True)
    date_cloture = models.DateTimeField(null=True, blank=True)
    commentaire = models.TextField(blank=True, default="")
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="campagnes_inventaire")
    resultat = models.JSONField(default=dict, blank=True, help_text="Bilan figé à la clôture")

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.reference = f"INV-{date.today().year}-{self.pk:03d}"
            super().save(update_fields=["reference"])
        else:
            super().save(*args, **kwargs)


class Constat(models.Model):
    campagne = models.ForeignKey(CampagneInventaire, on_delete=models.CASCADE, related_name="constats")
    exemplaire = models.ForeignKey(Exemplaire, on_delete=models.CASCADE, related_name="constats")
    emplacement = models.ForeignKey(Emplacement, on_delete=models.SET_NULL, null=True, blank=True, related_name="constats")
    condition = models.CharField(max_length=20, choices=Exemplaire.CONDITIONS, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    scanne_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="constats_inventaire")
    date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["campagne", "exemplaire"], name="unique_constat_campagne")]


# Keep old model for backward compatibility during migration
class Inventaire(models.Model):
    CATEGORIES = [
        ("Informatique", "Informatique"),
        ("Mobilier", "Mobilier"),
        ("Électronique", "Électronique"),
        ("Papeterie", "Papeterie"),
        ("Autre", "Autre"),
    ]
    STATUTS = [
        ("Disponible", "Disponible"),
        ("Occupee", "Occupee"),
        ("En panne", "En panne"),
    ]
    reference = models.CharField(max_length=20, unique=True, editable=False)
    article = models.CharField(max_length=150)
    categorie = models.CharField(max_length=100, choices=CATEGORIES)
    statut = models.CharField(max_length=20, choices=STATUTS, default="Disponible")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"INV-{self.pk:04d}"
            super().save(update_fields=["reference"])

    def __str__(self):
        return f"{self.article} ({self.reference})"

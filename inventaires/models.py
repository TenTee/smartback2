from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


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

    reference = models.CharField(max_length=30, unique=True, editable=False)
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    categorie = models.CharField(max_length=100, choices=CATEGORIES, default="Autre")
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
    def quantite_en_stock(self):
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
    notes = models.TextField(blank=True, default="")

    attributaire_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    attributaire_object_id = models.PositiveIntegerField(null=True, blank=True)
    attributaire = GenericForeignKey("attributaire_content_type", "attributaire_object_id")
    date_attribution = models.DateField(null=True, blank=True)

    date_acquisition = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.reference = f"EXP-{self.pk:05d}"
            super().save(update_fields=["reference"])
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.article.nom} - {self.reference}"

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

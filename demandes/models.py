from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class DemandeArticle(models.Model):
    STATUTS = [
        ("brouillon", "Brouillon"),
        ("soumise", "Soumise"),
        ("en_cours", "En cours de traitement"),
        ("approuvee", "Approuvée"),
        ("livree", "Livrée"),
        ("refusee", "Refusée"),
        ("annulee", "Annulée"),
    ]

    PRIORITES = [
        ("basse", "Basse"),
        ("normale", "Normale"),
        ("haute", "Haute"),
        ("urgente", "Urgente"),
    ]

    reference = models.CharField(max_length=50, unique=True, editable=False)
    objet = models.CharField(max_length=200, help_text="Objet de la demande")
    motif = models.TextField(blank=True, default="", help_text="Justification de la demande")
    priorite = models.CharField(max_length=20, choices=PRIORITES, default="normale")
    statut = models.CharField(max_length=20, choices=STATUTS, default="brouillon")

    demandeur_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True,
        related_name="demandes_articles"
    )
    demandeur_object_id = models.PositiveIntegerField(null=True, blank=True)
    demandeur = GenericForeignKey("demandeur_content_type", "demandeur_object_id")

    approbateur_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="demandes_approuvees"
    )
    approbateur_object_id = models.PositiveIntegerField(null=True, blank=True)
    approbateur = GenericForeignKey("approbateur_content_type", "approbateur_object_id")

    date_demande = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    date_livraison = models.DateTimeField(null=True, blank=True)
    commentaire_refus = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-date_demande"]

    def save(self, *args, **kwargs):
        if not self.reference:
            count = DemandeArticle.objects.count() + 1
            self.reference = f"DEM-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - {self.objet} ({self.get_statut_display()})"


class LigneDemande(models.Model):
    demande = models.ForeignKey(DemandeArticle, on_delete=models.CASCADE, related_name="lignes")
    article = models.ForeignKey("inventaires.Article", on_delete=models.CASCADE)
    quantite_demandee = models.PositiveIntegerField(default=1)
    quantite_accordee = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        unique_together = ["demande", "article"]

    def __str__(self):
        return f"{self.article.nom} x{self.quantite_demandee}"

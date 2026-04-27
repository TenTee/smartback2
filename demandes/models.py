from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class DemandeArticle(models.Model):
    STATUTS = [
        ("En attente", "En attente"),
        ("Approuvée", "Approuvée"),
        ("Refusée", "Refusée"),
        ("Terminée", "Terminée"),
    ]

    # Référence générée automatiquement
    reference = models.CharField(max_length=50, unique=True, editable=False)

    # Article demandé
    article = models.ForeignKey("inventaires.Inventaire", on_delete=models.CASCADE)

    # Date auto-générée
    date_demande = models.DateField(auto_now_add=True)

    # Statut de la demande
    statut = models.CharField(max_length=20, choices=STATUTS, default="En attente")

    # ✅ Relation générique vers Formateur ou Personnel
    demandeur_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    demandeur_object_id = models.PositiveIntegerField(null=True, blank=True)
    demandeur = GenericForeignKey("demandeur_content_type", "demandeur_object_id")

    def save(self, *args, **kwargs):
        # Génération automatique de la référence si elle n’existe pas
        if not self.reference:
            last_id = DemandeArticle.objects.count() + 1
            self.reference = f"DEM-{last_id:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - {self.article} ({self.statut})"
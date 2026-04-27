from django.db import models

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
        # Sauvegarde initiale pour obtenir un pk unique
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f"INV-{self.pk:04d}"  # ex: INV-0001
            super().save(update_fields=["reference"])

    def __str__(self):
        return f"{self.article} ({self.reference})"
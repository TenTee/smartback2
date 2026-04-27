from django.db import models

class Revenu(models.Model):
    CATEGORIES = [
        ("Inscription", "Frais d'inscription"),
        ("Examen", "Frais d'examen"),
        ("Subvention", "Subvention / Don"),
        ("Activite", "Activité extrascolaire"),
        ("Location", "Location d'infrastructure"),
        ("Vente", "Vente de produits/services"),
        ("Autres", "Autres revenus"),
    ]

    libelle = models.CharField(max_length=100)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    categorie = models.CharField(max_length=20, choices=CATEGORIES)
    date_entree = models.DateField(auto_now_add=True)
    responsable = models.CharField(max_length=100, blank=True, null=True)
    statut = models.CharField(
        max_length=20,
        choices=[("Validé", "Validé"), ("En attente", "En attente"), ("Rejeté", "Rejeté")],
        default="Validé"
    )
    justificatif = models.FileField(
        upload_to="revenus/justificatifs/",
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.libelle} - {self.montant} FCFA"
from django.db import models

class Personnel(models.Model):
    FONCTION_CHOICES = [
        ("responsableRh", "Responsable RH"),
        ("responsablePedagogique", "Responsable Pédagogique"),
        ("responsableLogistique", "Responsable Logistique"),
        ("stagiaire", "Stagiaire"),
        ("femmeMenage", "Femme de ménage"),
        ("responsableMarketing", "Responsable Marketing"),
    ]

    nom = models.CharField(max_length=100)
    contact = models.CharField(max_length=50)
    fonction = models.CharField(
        max_length=50,
        choices=FONCTION_CHOICES,
        default="stagiaire"  # ✅ valeur par défaut
    )
    date_inscription = models.DateTimeField(auto_now_add=True)
    salaire = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.nom} - {self.get_fonction_display()}"
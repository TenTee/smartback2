from django.db import models

SEMESTRE_CHOICES = [
    ("Semestre 1", "Semestre 1"),
    ("Semestre 2", "Semestre 2"),
]


class Module(models.Model):
    nom = models.CharField(max_length=200)
    duree = models.PositiveIntegerField(default=0, help_text="Durée en heures")
    coefficient = models.PositiveIntegerField(default=1, help_text="Coefficient du module")
    has_tp = models.BooleanField(default=False, help_text="Le module comporte-t-il un TP ?")
    pourcentage_cc = models.PositiveIntegerField(default=30, help_text="Pourcentage CC (0-100)")
    pourcentage_sn = models.PositiveIntegerField(default=70, help_text="Pourcentage SN (0-100)")
    pourcentage_tp = models.PositiveIntegerField(default=0, help_text="Pourcentage TP (0-100, si has_tp)")
    semestre = models.CharField(
        max_length=20,
        choices=SEMESTRE_CHOICES,
        default="Semestre 1",
        help_text="Semestre auquel appartient le cours",
    )

    def __str__(self):
        return self.nom

    def clean(self):
        # Validation des pourcentages
        if self.has_tp:
            total = (self.pourcentage_cc or 0) + (self.pourcentage_sn or 0) + (self.pourcentage_tp or 0)
            if total != 100:
                raise ValueError("La somme CC+SN+TP doit être égale à 100%.")
        else:
            total = (self.pourcentage_cc or 0) + (self.pourcentage_sn or 0)
            if total != 100:
                raise ValueError("La somme CC+SN doit être égale à 100%.")
            self.pourcentage_tp = 0

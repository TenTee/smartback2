from django.db import models

SEMESTRE_CHOICES = [
    ("Semestre 1", "Semestre 1"),
    ("Semestre 2", "Semestre 2"),
]


class Module(models.Model):
    nom = models.CharField(max_length=200)
    code_ue = models.CharField(max_length=20, blank=True, default="", help_text="Code UE (ex: UE101)")
    description = models.TextField(blank=True, default="")
    duree = models.PositiveIntegerField(default=0, help_text="Durée en heures")
    coefficient = models.PositiveIntegerField(default=1, help_text="Coefficient du module")
    credits = models.PositiveIntegerField(default=3, help_text="Nombre de crédits ECTS")
    semestre = models.CharField(
        max_length=20,
        choices=SEMESTRE_CHOICES,
        default="Semestre 1",
        help_text="Semestre auquel appartient le cours",
    )

    def __str__(self):
        return self.nom

from django.db import models


class DemandeAbsence(models.Model):
    STATUT_CHOICES = [
        ("en_attente", "En attente"),
        ("accepte", "Accepté"),
        ("refuse", "Refusé"),
    ]

    personnel = models.ForeignKey(
        "personnels.Personnel",
        on_delete=models.CASCADE,
        related_name="absences",
    )
    motif = models.TextField()
    date = models.DateField()
    preuve = models.FileField(
        upload_to="absences/preuves/",
        null=True,
        blank=True,
        verbose_name="Preuve (PDF ou image)",
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default="en_attente",
    )
    date_demande = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-date_demande"]

    def __str__(self):
        return f"{self.personnel.nom} - {self.date}"

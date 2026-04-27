from django.db import models
from etudiants.models import Etudiant
from modules.models import Module


class AssiduiteRecord(models.Model):
    TYPE_CHOICES = [
        ("ABSENCE", "Absence"),
        ("RETARD", "Retard"),
    ]

    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="assiduite")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="assiduite")
    date = models.DateField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    minutes_retard = models.PositiveIntegerField(null=True, blank=True)
    justifie = models.BooleanField(default=False)
    justificatif = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.etudiant.nom} - {self.type} - {self.date}"

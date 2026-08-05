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
    justificatif = models.FileField(upload_to="assiduite/justificatifs/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.justifie and not self.justificatif:
            raise ValidationError({"justificatif": "Un fichier justificatif est obligatoire pour justifier une absence ou un retard."})
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.etudiant.nom} - {self.type} - {self.date}"

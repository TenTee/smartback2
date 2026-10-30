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
    # Séance de l'emploi du temps concernée (le cours est fixé par la programmation du jour)
    emploi = models.ForeignKey("emploidutemps.EmploiDuTemps", on_delete=models.SET_NULL, null=True, blank=True, related_name="assiduite")
    heure_debut = models.TimeField(null=True, blank=True)
    heure_fin = models.TimeField(null=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    minutes_retard = models.PositiveIntegerField(null=True, blank=True)
    justifie = models.BooleanField(default=False)
    justificatif = models.FileField(upload_to="assiduite/justificatifs/", null=True, blank=True)
    # Justification écrite (motif, explication) : alternative ou complément au fichier
    justificatif_texte = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.justifie and not self.justificatif and not (self.justificatif_texte or "").strip():
            raise ValidationError({"justificatif": "Joignez un fichier ou écrivez la justification de l'absence ou du retard."})
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.etudiant.nom} - {self.type} - {self.date}"

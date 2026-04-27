# formations/models.py
from django.core.exceptions import ValidationError
from django.db import models
from modules.models import Module   # ✅ import du modèle Module

class Formation(models.Model):
    intitule = models.CharField(max_length=200)
    duree_mois = models.IntegerField(help_text="Durée de la formation en heures")
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Montant de la formation en FCFA"
    )
    frais_inscription = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Montant des frais d'inscription en FCFA"
    )
    nombre_niveaux = models.PositiveIntegerField(default=1, help_text="Nombre de niveaux (ex: 3 pour Licence)")
    modules = models.ManyToManyField(Module, related_name="formations", blank=True)  # ✅ relation

    def __str__(self):
        return self.intitule

class Niveau(models.Model):
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE, related_name="niveaux")
    cycle = models.ForeignKey(
        "academique.Cycle",
        on_delete=models.SET_NULL,
        related_name="niveaux",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=100) # ex: "Licence 1", "Master 2"
    modules = models.ManyToManyField(Module, related_name="niveaux", blank=True)

    def clean(self):
        if self.cycle_id and getattr(self.cycle.specialite.filiere, "formation_id", None):
            expected_formation_id = self.cycle.specialite.filiere.formation_id
            if self.formation_id != expected_formation_id:
                raise ValidationError("Le niveau doit appartenir à la formation liée à la filière académique.")

    def __str__(self):
        return f"{self.formation.intitule} - {self.nom}"

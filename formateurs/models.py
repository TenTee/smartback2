# formateurs/models.py
from django.db import models
from modules.models import Module

class Formateur(models.Model):
    nom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    contact = models.CharField(max_length=50)
    specialites = models.ManyToManyField(Module, related_name="formateurs")
    salaire = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # ✅ nouveau champ

    def __str__(self):
        return self.nom

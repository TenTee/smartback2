# formateurs/models.py
from django.db import models
from modules.models import Module


class Formateur(models.Model):
    TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('vacataire', 'Vacataire'),
    ]

    user = models.OneToOneField(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formateur_profile",
    )
    nom = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    contact = models.CharField(max_length=50)
    specialites = models.ManyToManyField(Module, related_name="formateurs")
    type_formateur = models.CharField(max_length=20, choices=TYPE_CHOICES, default='permanent')
    salaire = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    taux_horaire = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    @property
    def is_vacataire(self):
        return self.type_formateur == 'vacataire'

    def __str__(self):
        return self.nom


class CoursDocument(models.Model):
    formateur = models.ForeignKey(Formateur, on_delete=models.CASCADE, related_name="cours_documents")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="cours_documents")
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    fichier = models.FileField(upload_to="cours/documents/")
    est_visible_etudiants = models.BooleanField(default=False)
    date_upload = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_upload"]

    def __str__(self):
        return f"{self.titre} - {self.module.nom}"

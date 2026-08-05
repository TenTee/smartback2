from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Depense(models.Model):
    CATEGORIES = [
        ("Materiel", "Matériel pédagogique"),
        ("Entretien", "Entretien"),
        ("Logistique", "Logistique"),
        ("Activites", "Activités extrascolaires"),
        ("Autres", "Autres dépenses"),
    ]

    libelle = models.CharField(max_length=200)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    categorie = models.CharField(max_length=50, choices=CATEGORIES)
    date_depense = models.DateField(default=timezone.now)
    justificatif = models.FileField(
        upload_to="depenses/justificatifs/",
        null=True,
        blank=True
    )

    # ✅ Relation générique vers Formateur ou Personnel
    responsable_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    responsable_object_id = models.PositiveIntegerField(null=True, blank=True)
    responsable = GenericForeignKey("responsable_content_type", "responsable_object_id")

    statut = models.CharField(max_length=20, default="Validée")

    def __str__(self):
        if self.responsable:
            return f"{self.libelle} - {self.montant} FCFA (Responsable: {self.responsable.nom})"
        return f"{self.libelle} - {self.montant} FCFA (Sans responsable)"
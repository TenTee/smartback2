from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Paie(models.Model):
    STATUTS = [
        ("Payé", "Payé"),
        ("En attente", "En attente"),
    ]

    # ✅ Relation générique vers Formateur ou Personnel
    beneficiaire_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    beneficiaire_object_id = models.PositiveIntegerField(null=True, blank=True)
    beneficiaire = GenericForeignKey("beneficiaire_content_type", "beneficiaire_object_id")

    # Salaire (rempli automatiquement depuis le bénéficiaire choisi)
    salaire = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    date = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUTS, default="En attente")
    justificatif = models.FileField(
        upload_to="paie/justificatifs/",
        null=True,
        blank=True
    )


    def save(self, *args, **kwargs):
        # ✅ Si un bénéficiaire est sélectionné, on récupère son salaire automatiquement
        if self.beneficiaire and hasattr(self.beneficiaire, "salaire"):
            self.salaire = self.beneficiaire.salaire
        # ✅ Si aucun salaire n'est défini, on met 0 par défaut
        if self.salaire is None:
            self.salaire = 0
        super().save(*args, **kwargs)

    def __str__(self):
        if self.beneficiaire:
            return f"{self.beneficiaire.nom} - {self.salaire} FCFA ({self.statut})"
        return f"Paie sans bénéficiaire - {self.salaire} FCFA ({self.statut})"
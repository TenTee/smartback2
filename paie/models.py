from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from django.utils import timezone

class ParametresPaie(models.Model):
    """
    Singleton pour configurer le jour de paie.
    """
    jour_de_paie = models.PositiveIntegerField(default=25, help_text="Jour du mois pour la paie (1-31)")

    class Meta:
        verbose_name = "Paramètres de Paie"
        verbose_name_plural = "Paramètres de Paie"

    def save(self, *args, **kwargs):
        if not self.pk and ParametresPaie.objects.exists():
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Jour de paie : le {self.jour_de_paie}"

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
        is_new = self.pk is None
        old_statut = None
        if not is_new:
            old_statut = Paie.objects.get(pk=self.pk).statut

        # ✅ Récupération automatique du salaire
        if self.beneficiaire and hasattr(self.beneficiaire, "salaire") and not self.salaire:
            self.salaire = self.beneficiaire.salaire
        
        if self.salaire is None:
            self.salaire = 0

        super().save(*args, **kwargs)

        # ✅ Intégration Trésorerie : Création d'une dépense si statut passe à "Payé"
        if self.statut == "Payé" and (is_new or old_statut != "Payé"):
            try:
                Depense = apps.get_model('depenses', 'Depense')
                beneficiaire_nom = self.beneficiaire.nom if self.beneficiaire else "Inconnu"
                Depense.objects.create(
                    libelle=f"Salaire - {beneficiaire_nom} ({self.date.strftime('%B %Y')})",
                    montant=self.salaire,
                    categorie="Autres", # Ou une catégorie "Salaires" si elle existe
                    date_depense=timezone.now().date(),
                    statut="Validée",
                    responsable_content_type=self.beneficiaire_content_type,
                    responsable_object_id=self.beneficiaire_object_id
                )
            except Exception as e:
                print(f"Erreur lors de la création de la dépense : {e}")

    def __str__(self):
        if self.beneficiaire:
            return f"{self.beneficiaire.nom} - {self.salaire} FCFA ({self.statut})"
        return f"Paie sans bénéficiaire - {self.salaire} FCFA ({self.statut})"
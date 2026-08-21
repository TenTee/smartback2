from django.db import models

class Personnel(models.Model):
    nom = models.CharField(max_length=100)
    contact = models.CharField(max_length=50)
    fonction = models.CharField(
        max_length=50,
        default="stagiaire"  # ✅ valeur par défaut
    )
    date_inscription = models.DateTimeField(auto_now_add=True)
    date_embauche = models.DateField(null=True, blank=True, verbose_name="Date d'embauche")
    solde_conges_initial = models.PositiveIntegerField(default=20, verbose_name="Solde de congés annuel")
    jours_conges_supplementaires = models.PositiveIntegerField(default=0, verbose_name="Jours de congés supplémentaires")
    motif_conges_supplementaires = models.TextField(blank=True, default="", verbose_name="Motif des congés supplémentaires")
    solde_conges_restant = models.PositiveIntegerField(default=0, verbose_name="Solde de congés restant")
    salaire = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        original_extra_days = None
        if self.pk:
            original_extra_days = type(self).objects.only("jours_conges_supplementaires").get(
                pk=self.pk
            ).jours_conges_supplementaires

        # Initialise le solde restant si c'est un nouvel enregistrement
        if not self.pk and self.solde_conges_restant == 0:
            self.solde_conges_restant = self.solde_conges_initial + self.jours_conges_supplementaires
        elif original_extra_days is not None:
            self.solde_conges_restant += self.jours_conges_supplementaires - original_extra_days
        if self.jours_conges_supplementaires and not self.motif_conges_supplementaires.strip():
            from django.core.exceptions import ValidationError
            raise ValidationError({
                "motif_conges_supplementaires": "Le motif est obligatoire pour les congés supplémentaires."
            })
        super().save(*args, **kwargs)

    @property
    def anciennete_annees(self):
        from django.utils import timezone
        if not self.date_embauche:
            return 0
        delta = timezone.now().date() - self.date_embauche
        return delta.days // 365

    @property
    def est_eligible_conges(self):
        return self.anciennete_annees >= 1

    def __str__(self):
        return f"{self.nom} - {self.fonction}"
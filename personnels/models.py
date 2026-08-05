from django.db import models

class Personnel(models.Model):
    FONCTION_CHOICES = [
        ("responsableRh", "Responsable RH"),
        ("responsablePedagogique", "Responsable Pédagogique"),
        ("responsableLogistique", "Responsable Logistique"),
        ("stagiaire", "Stagiaire"),
        ("femmeMenage", "Femme de ménage"),
        ("responsableMarketing", "Responsable Marketing"),
    ]

    nom = models.CharField(max_length=100)
    contact = models.CharField(max_length=50)
    fonction = models.CharField(
        max_length=50,
        choices=FONCTION_CHOICES,
        default="stagiaire"  # ✅ valeur par défaut
    )
    date_inscription = models.DateTimeField(auto_now_add=True)
    date_embauche = models.DateField(null=True, blank=True, verbose_name="Date d'embauche")
    solde_conges_initial = models.PositiveIntegerField(default=0, verbose_name="Solde de congés annuel")
    solde_conges_restant = models.PositiveIntegerField(default=0, verbose_name="Solde de congés restant")
    salaire = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        # Initialise le solde restant si c'est un nouvel enregistrement
        if not self.pk and self.solde_conges_restant == 0:
            self.solde_conges_restant = self.solde_conges_initial
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
        return f"{self.nom} - {self.get_fonction_display()}"
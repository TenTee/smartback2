from django.db import models


class Conge(models.Model):
    date_debut = models.DateField()
    date_fin = models.DateField()
    type_conge = models.CharField(max_length=50)
    raison = models.TextField(null=True, blank=True)

    statut = models.CharField(
        max_length=20,
        default='en_attente',
        choices=[
            ('en_attente', 'En attente'),
            ('accepte', 'Accepté'),
            ('refuse', 'Refusé'),
        ]
    )

    personnel = models.ForeignKey(
        'personnels.Personnel',
        on_delete=models.CASCADE,
        related_name='conges'
    )

    def calculate_working_days(self, start_date, end_date):
        """
        Calcule le nombre de jours ouvrés (exclut Samedi et Dimanche)
        entre start_date et end_date (inclusif pour le début, exclusif pour la fin).
        """
        from datetime import timedelta
        days = (end_date - start_date).days
        working_days = 0
        for i in range(days):
            current_day = start_date + timedelta(days=i)
            # Monday=0, Tuesday=1, ..., Saturday=5, Sunday=6
            if current_day.weekday() < 5:
                working_days += 1
        return working_days

    def clean(self):
        from django.core.exceptions import ValidationError
        
        if self.date_debut and self.date_fin:
            if self.date_debut >= self.date_fin:
                raise ValidationError("La date de début doit être antérieure à la date de fin.")
            
            working_days = self.calculate_working_days(self.date_debut, self.date_fin)
            if working_days <= 0:
                raise ValidationError("La période choisie ne contient aucun jour ouvré (uniquement des weekends).")

        if self.personnel:
            # Check seniority
            if not self.personnel.est_eligible_conges:
                raise ValidationError(f"Ce membre du personnel n'est pas encore éligible aux congés (Ancienneté: {self.personnel.anciennete_annees} an(s)). Il faut au moins 1 an.")
            
            # Check balance if creating or approving
            working_days = self.calculate_working_days(self.date_debut, self.date_fin)
            if self.personnel.solde_conges_restant < working_days:
                raise ValidationError(f"Solde de congés insuffisant. Restant: {self.personnel.solde_conges_restant} jour(s) ouvré(s), Demandé: {working_days} jour(s).")

    def save(self, *args, **kwargs):
        # We check the status change to deduct from balance
        if self.pk:
            # Refresh from DB to get the current status before save
            original = Conge.objects.get(pk=self.pk)
            if original.statut != 'accepte' and self.statut == 'accepte':
                # Deduct from personnel balance (working days only)
                working_days = self.calculate_working_days(self.date_debut, self.date_fin)
                personnel = self.personnel
                personnel.solde_conges_restant -= working_days
                personnel.save(update_fields=['solde_conges_restant'])
        elif self.statut == 'accepte':
            # Case where a leave is created directly as 'accepted'
            working_days = self.calculate_working_days(self.date_debut, self.date_fin)
            personnel = self.personnel
            personnel.solde_conges_restant -= working_days
            personnel.save(update_fields=['solde_conges_restant'])
        
        # Validate before final save
        self.full_clean()
        super().save(*args, **kwargs)

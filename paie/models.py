from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from django.utils import timezone
from decimal import Decimal


class ParametresPaie(models.Model):
    jour_de_paie = models.PositiveIntegerField(default=25, help_text="Jour du mois pour la paie (1-31)")
    taux_cnps_employe = models.DecimalField(max_digits=5, decimal_places=2, default=4.20, help_text="Taux CNPS employé (%)")
    taux_cnps_employeur = models.DecimalField(max_digits=5, decimal_places=2, default=16.67, help_text="Taux CNPS employeur (%)")
    taux_irpp = models.DecimalField(max_digits=5, decimal_places=2, default=10.00, help_text="Taux IRPP par défaut (%)")

    class Meta:
        verbose_name = "Paramètres de Paie"
        verbose_name_plural = "Paramètres de Paie"

    def save(self, *args, **kwargs):
        if not self.pk and ParametresPaie.objects.exists():
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Jour de paie : le {self.jour_de_paie}"


class Prime(models.Model):
    TYPE_CHOICES = [
        ("transport", "Prime de transport"),
        ("logement", "Prime de logement"),
        ("rendement", "Prime de rendement"),
        ("anciennete", "Prime d'ancienneté"),
        ("responsabilite", "Prime de responsabilité"),
        ("risque", "Prime de risque"),
        ("panier", "Prime de panier"),
        ("heures_sup", "Heures supplémentaires"),
        ("autre", "Autre"),
    ]

    beneficiaire_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    beneficiaire_object_id = models.PositiveIntegerField()
    beneficiaire = GenericForeignKey("beneficiaire_content_type", "beneficiaire_object_id")

    type_prime = models.CharField(max_length=30, choices=TYPE_CHOICES)
    libelle = models.CharField(max_length=200, blank=True)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    est_permanente = models.BooleanField(default=True, help_text="Appliquée chaque mois automatiquement")
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    est_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Prime / Indemnité"
        verbose_name_plural = "Primes / Indemnités"
        ordering = ['-est_active', 'type_prime']

    def __str__(self):
        return f"{self.get_type_prime_display()} - {self.montant} FCFA"


class Retenue(models.Model):
    TYPE_CHOICES = [
        ("cnps", "CNPS"),
        ("irpp", "IRPP"),
        ("avance", "Remboursement avance"),
        ("absence", "Retenue pour absence"),
        ("pret", "Remboursement prêt"),
        ("autre", "Autre"),
    ]

    beneficiaire_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    beneficiaire_object_id = models.PositiveIntegerField()
    beneficiaire = GenericForeignKey("beneficiaire_content_type", "beneficiaire_object_id")

    type_retenue = models.CharField(max_length=30, choices=TYPE_CHOICES)
    libelle = models.CharField(max_length=200, blank=True)
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    est_permanente = models.BooleanField(default=True)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    est_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Retenue"
        verbose_name_plural = "Retenues"
        ordering = ['-est_active', 'type_retenue']

    def __str__(self):
        return f"{self.get_type_retenue_display()} - {self.montant} FCFA"


class AvanceSalaire(models.Model):
    STATUT_CHOICES = [
        ("en_cours", "En cours de remboursement"),
        ("remboursee", "Remboursée"),
        ("annulee", "Annulée"),
    ]

    beneficiaire_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    beneficiaire_object_id = models.PositiveIntegerField()
    beneficiaire = GenericForeignKey("beneficiaire_content_type", "beneficiaire_object_id")

    montant_total = models.DecimalField(max_digits=12, decimal_places=2)
    montant_rembourse = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    nombre_echeances = models.PositiveIntegerField(default=1, help_text="Nombre de mois pour rembourser")
    montant_echeance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    motif = models.TextField(blank=True)
    date_demande = models.DateField(auto_now_add=True)
    date_debut_remboursement = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="en_cours")

    class Meta:
        verbose_name = "Avance sur salaire"
        verbose_name_plural = "Avances sur salaire"
        ordering = ['-date_demande']

    def save(self, *args, **kwargs):
        if self.nombre_echeances > 0:
            self.montant_echeance = self.montant_total / self.nombre_echeances
        if self.montant_rembourse >= self.montant_total:
            self.statut = "remboursee"
        super().save(*args, **kwargs)

    @property
    def solde_restant(self):
        return max(Decimal('0'), self.montant_total - self.montant_rembourse)

    def __str__(self):
        nom = getattr(self.beneficiaire, 'nom', 'N/A') if self.beneficiaire else 'N/A'
        return f"Avance {nom} - {self.montant_total} FCFA ({self.statut})"


class CampagnePaie(models.Model):
    STATUT_CHOICES = [
        ("brouillon", "Brouillon"),
        ("validee", "Validée"),
        ("payee", "Payée"),
        ("annulee", "Annulée"),
    ]

    reference = models.CharField(max_length=50, unique=True, blank=True)
    mois = models.PositiveIntegerField()
    annee = models.PositiveIntegerField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="brouillon")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_paiement = models.DateTimeField(null=True, blank=True)
    total_brut = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_primes = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_retenues = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    nombre_bulletins = models.PositiveIntegerField(default=0)
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "Campagne de paie"
        verbose_name_plural = "Campagnes de paie"
        ordering = ['-annee', '-mois']
        unique_together = ['mois', 'annee']

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"CAMP-{self.annee}-{self.mois:02d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Campagne {self.mois:02d}/{self.annee} - {self.get_statut_display()}"


class BulletinPaie(models.Model):
    STATUT_CHOICES = [
        ("genere", "Généré"),
        ("valide", "Validé"),
        ("paye", "Payé"),
        ("annule", "Annulé"),
    ]

    campagne = models.ForeignKey(CampagnePaie, on_delete=models.CASCADE, related_name="bulletins", null=True, blank=True)

    beneficiaire_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    beneficiaire_object_id = models.PositiveIntegerField()
    beneficiaire = GenericForeignKey("beneficiaire_content_type", "beneficiaire_object_id")

    mois = models.PositiveIntegerField()
    annee = models.PositiveIntegerField()
    salaire_base = models.DecimalField(max_digits=12, decimal_places=2)
    total_primes = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_retenues = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    salaire_brut = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    salaire_net = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    detail_primes = models.JSONField(default=list, blank=True)
    detail_retenues = models.JSONField(default=list, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default="genere")
    date_generation = models.DateTimeField(auto_now_add=True)
    date_paiement = models.DateTimeField(null=True, blank=True)
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "Bulletin de paie"
        verbose_name_plural = "Bulletins de paie"
        ordering = ['-annee', '-mois', 'beneficiaire_object_id']

    def calculer(self):
        self.salaire_brut = self.salaire_base + self.total_primes
        self.salaire_net = self.salaire_brut - self.total_retenues
        if self.salaire_net < 0:
            self.salaire_net = Decimal('0')

    def save(self, *args, **kwargs):
        self.calculer()
        super().save(*args, **kwargs)

    def __str__(self):
        nom = getattr(self.beneficiaire, 'nom', 'N/A') if self.beneficiaire else 'N/A'
        return f"Bulletin {nom} - {self.mois:02d}/{self.annee} ({self.statut})"


class Paie(models.Model):
    STATUTS = [
        ("Payé", "Payé"),
        ("En attente", "En attente"),
    ]

    beneficiaire_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    beneficiaire_object_id = models.PositiveIntegerField(null=True, blank=True)
    beneficiaire = GenericForeignKey("beneficiaire_content_type", "beneficiaire_object_id")

    salaire = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    date = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUTS, default="En attente")
    justificatif = models.FileField(upload_to="paie/justificatifs/", null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_statut = None
        if not is_new:
            old_statut = Paie.objects.get(pk=self.pk).statut

        if self.beneficiaire and hasattr(self.beneficiaire, "salaire") and not self.salaire:
            self.salaire = self.beneficiaire.salaire

        if self.salaire is None:
            self.salaire = 0

        super().save(*args, **kwargs)

        if self.statut == "Payé" and (is_new or old_statut != "Payé"):
            try:
                Depense = apps.get_model('depenses', 'Depense')
                beneficiaire_nom = self.beneficiaire.nom if self.beneficiaire else "Inconnu"
                Depense.objects.create(
                    libelle=f"Salaire - {beneficiaire_nom} ({self.date.strftime('%B %Y')})",
                    montant=self.salaire,
                    categorie="Autres",
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

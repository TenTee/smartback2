"""Trésorerie : comptes (caisses, banques, mobile money), opérations (recettes, dépenses, virements),
circuit de validation des dépenses, clôtures de caisse, rapprochements bancaires et budget."""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum

ZERO = Decimal("0")


class CompteTresorerie(models.Model):
    CAISSE, BANQUE, MOBILE = "caisse", "banque", "mobile"
    TYPES = [(CAISSE, "Caisse (espèces)"), (BANQUE, "Compte bancaire"), (MOBILE, "Mobile Money")]

    nom = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=TYPES, default=CAISSE)
    banque = models.CharField(max_length=120, blank=True, default="", help_text="Banque / opérateur")
    numero = models.CharField(max_length=60, blank=True, default="", help_text="N° de compte / de téléphone")
    solde_initial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    date_solde_initial = models.DateField(null=True, blank=True)
    actif = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ordre", "id"]
        verbose_name = "Compte de trésorerie"

    def __str__(self):
        return self.nom

    def solde(self, jusqu_au=None):
        """Solde = initial + recettes − dépenses ± virements (opérations validées)."""
        ops = Operation.objects.filter(statut=Operation.VALIDEE)
        if jusqu_au:
            ops = ops.filter(date__lte=jusqu_au)
        entrees = ops.filter(Q(type=Operation.RECETTE, compte=self) | Q(type=Operation.VIREMENT, compte_destination=self))
        sorties = ops.filter(Q(type=Operation.DEPENSE, compte=self) | Q(type=Operation.VIREMENT, compte=self))
        e = entrees.aggregate(t=Sum("montant"))["t"] or ZERO
        s = sorties.aggregate(t=Sum("montant"))["t"] or ZERO
        return Decimal(self.solde_initial) + e - s

    def annee_initiale_id(self):
        """Année académique à laquelle appartient le solde initial (celle qui contient sa date, sinon la première)."""
        from academique.models import AnneeAcademique
        qs = AnneeAcademique.objects.exclude(date_debut__isnull=True)
        if self.date_solde_initial:
            a = qs.filter(date_debut__lte=self.date_solde_initial, date_fin__gte=self.date_solde_initial).first()
            if a:
                return a.id
        a = qs.order_by("date_debut").first() or AnneeAcademique.objects.order_by("libelle").first()
        return a.id if a else None

    def solde_annee(self, annee, jusqu_au=None):
        """Argent de l'année académique sur ce compte : chaque année a sa propre caisse.

        = solde initial (s'il appartient à l'année) + recettes − dépenses ± virements de l'année
          + reports reçus d'autres années − reports cédés à d'autres années.
        """
        if annee is None:
            return self.solde(jusqu_au)
        from academique.models import AnneeAcademique
        if not hasattr(annee, "date_fin"):
            annee = AnneeAcademique.objects.filter(pk=annee).first()
            if annee is None:
                return self.solde(jusqu_au)
        aid = annee.id
        ops = Operation.objects.filter(statut=Operation.VALIDEE)
        dans = ops.filter(annee_academique_id=aid)
        if jusqu_au:
            dans = dans.filter(date__lte=jusqu_au)
        e = dans.filter(Q(type=Operation.RECETTE, compte=self) | Q(type=Operation.VIREMENT, compte_destination=self)
                        | Q(type=Operation.REPORT, compte=self)).aggregate(t=Sum("montant"))["t"] or ZERO
        s = dans.filter(Q(type=Operation.DEPENSE, compte=self) | Q(type=Operation.VIREMENT, compte=self)).aggregate(t=Sum("montant"))["t"] or ZERO
        cedes = ops.filter(type=Operation.REPORT, annee_origine_id=aid, compte=self)
        # Un report fait après la fin de l'année d'origine est compté à sa date de fin (bilan de fin d'année).
        if jusqu_au and not (annee.date_fin and jusqu_au >= annee.date_fin):
            cedes = cedes.filter(date__lte=jusqu_au)
        cede = cedes.aggregate(t=Sum("montant"))["t"] or ZERO
        base = ZERO
        if self.annee_initiale_id() == aid:
            limite = max(jusqu_au, annee.date_debut) if (jusqu_au and annee.date_debut) else jusqu_au
            if not limite or not self.date_solde_initial or self.date_solde_initial <= limite:
                base = Decimal(self.solde_initial)
        return base + e - s - cede


class CategorieFinance(models.Model):
    RECETTE, DEPENSE = "recette", "depense"
    SENS = [(RECETTE, "Recette"), (DEPENSE, "Dépense")]

    code = models.CharField(max_length=20, unique=True, help_text="Code interne (ex. SCO-FOR) ou compte OHADA (ex. 706)")
    libelle = models.CharField(max_length=150)
    sens = models.CharField(max_length=10, choices=SENS)
    compte_comptable = models.CharField(max_length=20, blank=True, default="", help_text="Compte du plan OHADA (indicatif)")
    actif = models.BooleanField(default=True)
    systeme = models.BooleanField(default=False, help_text="Utilisée par les opérations automatiques (non supprimable)")
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sens", "ordre", "libelle"]
        verbose_name = "Catégorie financière"

    def __str__(self):
        return f"{self.libelle} ({self.get_sens_display()})"


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200)
    contact = models.CharField(max_length=120, blank=True, default="", help_text="Personne à contacter")
    telephone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    adresse = models.CharField(max_length=255, blank=True, default="")
    niu = models.CharField(max_length=50, blank=True, default="", help_text="N° d'identifiant unique (contribuable)")
    rccm = models.CharField(max_length=50, blank=True, default="")
    banque = models.CharField(max_length=200, blank=True, default="", help_text="Coordonnées bancaires / mobile money")
    notes = models.TextField(blank=True, default="")
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Operation(models.Model):
    RECETTE, DEPENSE, VIREMENT, REPORT = "recette", "depense", "virement", "report"
    TYPES = [(RECETTE, "Recette"), (DEPENSE, "Dépense"), (VIREMENT, "Virement interne"),
             (REPORT, "Report d'une autre année")]

    EN_ATTENTE, APPROUVEE, VALIDEE, REJETEE, ANNULEE = "en_attente", "approuvee", "validee", "rejetee", "annulee"
    STATUTS = [
        (EN_ATTENTE, "À approuver"),
        (APPROUVEE, "Approuvée — à payer"),
        (VALIDEE, "Validée"),
        (REJETEE, "Rejetée"),
        (ANNULEE, "Annulée"),
    ]
    MODES = [
        ("especes", "Espèces"), ("cheque", "Chèque"), ("virement", "Virement bancaire"),
        ("mobile_money", "Mobile Money"), ("carte", "Carte bancaire"), ("autre", "Autre"),
    ]
    SOURCES = [("manuel", "Saisie"), ("scolarite", "Scolarité"), ("paie", "Paie"), ("ancien", "Reprise des données")]

    numero = models.CharField(max_length=30, unique=True)
    type = models.CharField(max_length=10, choices=TYPES)
    date = models.DateField()
    montant = models.DecimalField(max_digits=14, decimal_places=2)
    compte = models.ForeignKey(CompteTresorerie, on_delete=models.PROTECT, null=True, blank=True, related_name="operations")
    compte_destination = models.ForeignKey(CompteTresorerie, on_delete=models.PROTECT, null=True, blank=True, related_name="operations_entrantes")
    categorie = models.ForeignKey(CategorieFinance, on_delete=models.PROTECT, null=True, blank=True, related_name="operations")
    libelle = models.CharField(max_length=255)
    tiers = models.CharField(max_length=200, blank=True, default="", help_text="Payeur / bénéficiaire")
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.SET_NULL, null=True, blank=True, related_name="operations")
    etudiant = models.ForeignKey("etudiants.Etudiant", on_delete=models.SET_NULL, null=True, blank=True, related_name="operations_tresorerie")
    mode = models.CharField(max_length=20, choices=MODES, default="especes")
    reference = models.CharField(max_length=100, blank=True, default="", help_text="N° de chèque, de transaction, de facture…")
    piece_jointe = models.FileField(upload_to="tresorerie/pieces/", null=True, blank=True)
    statut = models.CharField(max_length=12, choices=STATUTS, default=VALIDEE, db_index=True)
    source = models.CharField(max_length=12, choices=SOURCES, default="manuel")
    source_type = models.CharField(max_length=30, blank=True, default="")
    source_id = models.PositiveIntegerField(null=True, blank=True)
    annee_academique = models.ForeignKey("academique.AnneeAcademique", on_delete=models.SET_NULL, null=True, blank=True, related_name="operations_tresorerie")
    # Report : argent repris d'une année précédente (annee_origine) pour l'année annee_academique.
    annee_origine = models.ForeignKey("academique.AnneeAcademique", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports_cedes")
    date_echeance = models.DateField(null=True, blank=True, help_text="Date limite de paiement (dépense)")
    notes = models.TextField(blank=True, default="")
    motif_rejet = models.CharField(max_length=255, blank=True, default="")
    rapprochement = models.ForeignKey("Rapprochement", on_delete=models.SET_NULL, null=True, blank=True, related_name="operations")
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="operations_creees")
    cree_le = models.DateTimeField(auto_now_add=True)
    approuve_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="operations_approuvees")
    approuve_le = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="operations_validees")
    valide_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["type", "statut", "date"]), models.Index(fields=["source_type", "source_id"])]
        constraints = [
            models.UniqueConstraint(fields=["source_type", "source_id"], condition=~Q(source_type=""), name="unique_operation_source"),
        ]

    def __str__(self):
        return f"{self.numero} — {self.libelle}"


class ClotureCaisse(models.Model):
    """Arrêté de caisse : solde théorique vs solde compté. Les opérations antérieures sont verrouillées."""

    compte = models.ForeignKey(CompteTresorerie, on_delete=models.CASCADE, related_name="clotures")
    date = models.DateField()
    solde_theorique = models.DecimalField(max_digits=14, decimal_places=2)
    solde_reel = models.DecimalField(max_digits=14, decimal_places=2)
    ecart = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    billetage = models.JSONField(default=dict, blank=True, help_text="Détail des billets et pièces comptés")
    commentaire = models.TextField(blank=True, default="")
    operation_ecart = models.ForeignKey(Operation, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [models.UniqueConstraint(fields=["compte", "date"], name="unique_cloture_compte_date")]


class Rapprochement(models.Model):
    """Rapprochement bancaire : opérations pointées avec le relevé de la banque."""

    compte = models.ForeignKey(CompteTresorerie, on_delete=models.CASCADE, related_name="rapprochements")
    date_releve = models.DateField()
    solde_releve = models.DecimalField(max_digits=14, decimal_places=2)
    solde_pointe = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ecart = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commentaire = models.TextField(blank=True, default="")
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_releve", "-id"]


class Budget(models.Model):
    annee_academique = models.OneToOneField("academique.AnneeAcademique", on_delete=models.CASCADE, related_name="budget")
    commentaire = models.TextField(blank=True, default="")
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)


class LigneBudget(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lignes")
    categorie = models.ForeignKey(CategorieFinance, on_delete=models.CASCADE, related_name="lignes_budget")
    montant_prevu = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["budget", "categorie"], name="unique_ligne_budget")]

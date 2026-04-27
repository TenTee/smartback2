from django.core.exceptions import ValidationError
from django.db import models

from formateurs.models import Formateur
from formations.models import Formation, Niveau
from modules.models import Module

from .services.hierarchy import generate_classe_name, validate_classe_hierarchy


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class NamedDescriptionModel(TimeStampedModel):
    description = models.TextField(blank=True, default="")

    class Meta:
        abstract = True

    @property
    def name(self):
        return getattr(self, "nom", getattr(self, "libelle", ""))


class Faculte(NamedDescriptionModel):
    nom = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["nom"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.nom = self.nom.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Domaine(NamedDescriptionModel):
    faculte = models.ForeignKey(Faculte, on_delete=models.CASCADE, related_name="domaines", db_index=True)
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["faculte__nom", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["faculte", "nom"], name="unique_domaine_per_faculte"),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.nom = self.nom.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.faculte.nom} - {self.nom}"


class Filiere(NamedDescriptionModel):
    domaine = models.ForeignKey(Domaine, on_delete=models.CASCADE, related_name="filieres", db_index=True)
    formation = models.OneToOneField(
        "formations.Formation",
        on_delete=models.PROTECT,
        related_name="academic_filiere",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["domaine__nom", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["domaine", "nom"], name="unique_filiere_per_domaine"),
        ]

    def clean(self):
        if self.formation_id and not self.nom:
            self.nom = self.formation.intitule

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.nom = self.nom.strip()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Specialite(NamedDescriptionModel):
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="specialites", db_index=True)
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["filiere__nom", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["filiere", "nom"], name="unique_specialite_per_filiere"),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.nom = self.nom.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class Cycle(NamedDescriptionModel):
    specialite = models.ForeignKey(Specialite, on_delete=models.CASCADE, related_name="cycles", db_index=True)
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    ordre = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["specialite__nom", "ordre", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["specialite", "nom"], name="unique_cycle_per_specialite"),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.nom = self.nom.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.specialite.nom} - {self.nom}"


class AnneeAcademique(NamedDescriptionModel):
    libelle = models.CharField(max_length=9, unique=True, help_text="Ex: 2024-2025")
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    est_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-libelle"]

    def __str__(self):
        return self.libelle

    def clean(self):
        if self.date_debut and self.date_fin and self.date_debut >= self.date_fin:
            raise ValidationError({"date_fin": "La date de fin doit être postérieure à la date de début."})

    def save(self, *args, **kwargs):
        self.libelle = self.libelle.strip()
        self.full_clean()
        super().save(*args, **kwargs)


class Classe(NamedDescriptionModel):
    specialite = models.ForeignKey(Specialite, on_delete=models.CASCADE, related_name="classes", db_index=True)
    cycle = models.ForeignKey(Cycle, on_delete=models.PROTECT, related_name="classes", db_index=True)
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name="classes", db_index=True)
    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.PROTECT,
        related_name="classes",
        db_index=True,
    )
    modules = models.ManyToManyField(Module, related_name="classes", blank=True)
    nom = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["annee_academique__libelle", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["specialite", "niveau", "annee_academique"],
                name="unique_classe_per_specialite_niveau_annee",
            ),
        ]
        indexes = [
            models.Index(fields=["specialite", "niveau", "annee_academique"], name="classe_lookup_idx"),
        ]

    def __str__(self):
        return self.nom

    def clean(self):
        validate_classe_hierarchy(self)

    def save(self, *args, **kwargs):
        self.full_clean()
        self.nom = generate_classe_name(self.specialite, self.niveau, self.annee_academique)
        super().save(*args, **kwargs)

        if self.modules.exists():
            return

        base_modules = self.niveau.modules.all() if hasattr(self.niveau, "modules") else Module.objects.none()
        if not base_modules.exists():
            filiere_formation = getattr(self.specialite.filiere, "formation", None)
            if filiere_formation:
                base_modules = filiere_formation.modules.all()

        if base_modules.exists():
            self.modules.set(base_modules)


class Semestre(NamedDescriptionModel):
    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.CASCADE,
        related_name="semestres",
        db_index=True,
    )
    nom = models.CharField(max_length=100)
    ordre = models.PositiveIntegerField(default=1)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["annee_academique__libelle", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["annee_academique", "ordre"], name="unique_semestre_per_year_order"),
        ]

    def __str__(self):
        return f"{self.annee_academique.libelle} - {self.nom}"

    def clean(self):
        if self.date_debut and self.date_fin and self.date_debut >= self.date_fin:
            raise ValidationError({"date_fin": "La date de fin doit être postérieure à la date de début."})

    def save(self, *args, **kwargs):
        self.nom = self.nom.strip()
        self.full_clean()
        super().save(*args, **kwargs)


class Evaluation(NamedDescriptionModel):
    TYPE_CHOICES = [
        ("CC", "CC"),
        ("EXAMEN", "Examen"),
        ("TP", "TP"),
        ("RATTRAPAGE", "Rattrapage"),
        ("AUTRE", "Autre"),
    ]

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="evaluations", db_index=True)
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="evaluations", db_index=True)
    semestre = models.ForeignKey(
        Semestre,
        on_delete=models.SET_NULL,
        related_name="evaluations",
        null=True,
        blank=True,
    )
    type_evaluation = models.CharField(max_length=20, choices=TYPE_CHOICES)
    libelle = models.CharField(max_length=150)
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    date_evaluation = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-date_evaluation", "libelle"]
        constraints = [
            models.UniqueConstraint(
                fields=["classe", "module", "type_evaluation", "libelle"],
                name="unique_evaluation_signature",
            ),
        ]

    def __str__(self):
        return f"{self.libelle} - {self.classe.nom}"

    @property
    def name(self):
        return self.libelle

    def clean(self):
        if self.module_id and self.classe_id and not self.classe.modules.filter(pk=self.module_id).exists():
            raise ValidationError({"module": "Le module sélectionné n'est pas rattaché à la classe."})
        if self.semestre_id and self.semestre.annee_academique_id != self.classe.annee_academique_id:
            raise ValidationError({"semestre": "Le semestre doit appartenir à la même année académique que la classe."})

    def save(self, *args, **kwargs):
        self.libelle = self.libelle.strip()
        self.full_clean()
        super().save(*args, **kwargs)


class Affectation(TimeStampedModel):
    enseignant = models.ForeignKey(Formateur, on_delete=models.CASCADE, related_name="affectations", db_index=True)
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="affectations", db_index=True)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="affectations", db_index=True)

    class Meta:
        ordering = ["classe__nom", "module__nom"]
        constraints = [
            models.UniqueConstraint(fields=["enseignant", "module", "classe"], name="unique_affectation"),
        ]

    def __str__(self):
        return f"{self.enseignant.nom} - {self.module.nom} - {self.classe.nom}"

    def clean(self):
        if self.module_id and self.classe_id and not self.classe.modules.filter(pk=self.module_id).exists():
            raise ValidationError({"module": "Le module affecté doit appartenir à la classe."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PreInscription(NamedDescriptionModel):
    STATUS_CHOICES = [
        ("EN_ATTENTE", "En attente"),
        ("APPROUVEE", "Approuvée"),
        ("REJETEE", "Rejetée"),
    ]

    nom_candidat = models.CharField(max_length=150)
    prenom_candidat = models.CharField(max_length=150)
    email = models.EmailField()
    telephone = models.CharField(max_length=20)
    filiere_souhaitee = models.ForeignKey(
        Filiere, on_delete=models.SET_NULL, null=True, blank=True, related_name="pre_inscriptions"
    )
    formation_souhaitee = models.ForeignKey(
        Formation, on_delete=models.SET_NULL, null=True, blank=True, related_name="pre_inscriptions"
    )
    niveau_souhaite = models.ForeignKey(
        Niveau, on_delete=models.SET_NULL, null=True, blank=True, related_name="pre_inscriptions"
    )
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default="EN_ATTENTE")
    bulletin = models.FileField(upload_to="pre_inscriptions/bulletins/", null=True, blank=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def name(self):
        return f"{self.nom_candidat} {self.prenom_candidat}".strip()

    def __str__(self):
        return f"{self.nom_candidat} {self.prenom_candidat} - {self.statut}"

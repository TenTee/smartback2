# pyrefly: ignore [missing-import]
from django.core.exceptions import ValidationError
# pyrefly: ignore [missing-import]
from django.db import models

from formateurs.models import Formateur
from modules.models import Module

# We remove the import from formations as we will delete that app
# from formations.models import Formation, Niveau 

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


class ParametresGlobaux(TimeStampedModel):
    pourcentage_cc = models.PositiveIntegerField(default=30, help_text="Pourcentage de la note CC (0-100)")
    pourcentage_sn = models.PositiveIntegerField(default=70, help_text="Pourcentage de la note SN (0-100)")

    class Meta:
        verbose_name = "Paramètre Global"
        verbose_name_plural = "Paramètres Globaux"

    def clean(self):
        if self.pourcentage_cc + self.pourcentage_sn != 100:
            raise ValidationError("La somme CC+SN doit être égale à 100%.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_parametres(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={"pourcentage_cc": 30, "pourcentage_sn": 70})
        return obj


class ConfigurationEtablissement(TimeStampedModel):
    nom = models.CharField(max_length=255, default="SmartCampus")
    logo = models.ImageField(upload_to="etablissement/logos/", null=True, blank=True)
    logo_entete = models.ImageField(upload_to="etablissement/logos/", null=True, blank=True, help_text="Logo pour l'en-tête des documents (relevés, certificats)")
    adresse = models.TextField(blank=True)
    ville = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    site_web = models.URLField(blank=True)
    
    # Apparence
    couleur_primaire = models.CharField(max_length=20, default="#193A7F")
    couleur_secondaire = models.CharField(max_length=20, default="#2A52A1")
    couleur_texte = models.CharField(max_length=20, default="#333333", blank=True)
    typographie = models.CharField(max_length=100, default="'Inter', sans-serif")

    # Slogan
    slogan = models.CharField(max_length=255, blank=True, default="Former aujourd'hui, construire demain.")

    # Direction
    nom_directeur = models.CharField(max_length=255, blank=True)
    titre_directeur = models.CharField(max_length=255, blank=True, default="Le Directeur Général")
    signature_directeur = models.ImageField(upload_to="etablissement/signatures/", null=True, blank=True)

    class Meta:
        verbose_name = "Configuration de l'Établissement"
        verbose_name_plural = "Configuration de l'Établissement"

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return self.nom


class UniversiteTutelle(NamedDescriptionModel):
    nom = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Université de Tutelle"
        verbose_name_plural = "Universités de Tutelle"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Departement(NamedDescriptionModel):
    universite_tutelle = models.ForeignKey(UniversiteTutelle, on_delete=models.CASCADE, related_name="departements")
    nom = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Département"
        verbose_name_plural = "Départements"
        ordering = ["universite_tutelle__nom", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["universite_tutelle", "nom"], name="unique_departement_per_universite"),
        ]

    def __str__(self):
        return f"{self.universite_tutelle.nom} - {self.nom}"


class Filiere(NamedDescriptionModel):
    departement = models.ForeignKey(Departement, on_delete=models.CASCADE, related_name="filieres")
    nom = models.CharField(max_length=200)
    responsable_nom = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name = "Filière"
        verbose_name_plural = "Filières"
        ordering = ["departement__nom", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["departement", "nom"], name="unique_filiere_per_departement"),
        ]

    def __str__(self):
        return self.nom


class CycleGlobal(NamedDescriptionModel):
    nom = models.CharField(max_length=100, unique=True, help_text="Ex: BTS, Licence, Master")
    code = models.CharField(max_length=50, blank=True)
    heure_pause_debut = models.TimeField(default="12:00:00")
    heure_pause_fin = models.TimeField(default="13:00:00")
    heure_debut_journee = models.TimeField(default="08:00:00")
    heure_fin_journee = models.TimeField(default="18:00:00")

    class Meta:
        verbose_name = "Cycle Global"
        verbose_name_plural = "Cycles Globaux"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Cycle(NamedDescriptionModel):
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="cycles")
    type_cycle = models.ForeignKey(CycleGlobal, on_delete=models.PROTECT, related_name="cycles_acad", null=True, blank=True)
    nom = models.CharField(max_length=100, blank=True) # Will be auto-filled from type_cycle if empty
    code = models.CharField(max_length=50, blank=True)
    ordre = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Cycle"
        verbose_name_plural = "Cycles"
        ordering = ["filiere__nom", "ordre", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["filiere", "type_cycle"], name="unique_cycle_type_per_filiere"),
        ]

    def save(self, *args, **kwargs):
        if self.type_cycle and not self.nom:
            self.nom = self.type_cycle.nom
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.filiere.nom} - {self.nom}"


class Niveau(NamedDescriptionModel):
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE, related_name="niveaux")
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True)
    ordre = models.PositiveIntegerField(default=1)
    modules = models.ManyToManyField(Module, related_name="niveaux_academique", blank=True)

    class Meta:
        verbose_name = "Niveau"
        verbose_name_plural = "Niveaux"
        ordering = ["cycle__nom", "ordre", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["cycle", "nom"], name="unique_niveau_per_cycle"),
        ]

    @property
    def filiere(self):
        return self.cycle.filiere

    def __str__(self):
        return f"{self.cycle.filiere.nom} - {self.cycle.nom} - {self.nom}"


class CourseAssignment(TimeStampedModel):
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="course_assignments")
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE, related_name="course_assignments")
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name="course_assignments")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="course_assignments")

    class Meta:
        verbose_name = "Attribution de Cours"
        verbose_name_plural = "Attributions de Cours"
        ordering = ["filiere__nom", "cycle__ordre", "niveau__nom", "module__nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["filiere", "cycle", "niveau", "module"],
                name="unique_course_assignment_per_path",
            ),
        ]

    def __str__(self):
        return f"{self.filiere.nom} / {self.cycle.nom} / {self.niveau.nom} / {self.module.nom}"

    def clean(self):
        if self.cycle_id and self.cycle.filiere_id != self.filiere_id:
            raise ValidationError({"cycle": "Le cycle doit appartenir à la filière sélectionnée."})
        if self.niveau_id and self.niveau.cycle_id != self.cycle_id:
            raise ValidationError({"niveau": "Le niveau doit appartenir au cycle sélectionné."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.niveau.modules.add(self.module)


class AnneeAcademique(NamedDescriptionModel):
    libelle = models.CharField(max_length=15, unique=True, help_text="Ex: 2024-2025")
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    est_active = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Année Académique"
        verbose_name_plural = "Années Académiques"
        ordering = ["-libelle"]

    def __str__(self):
        return self.libelle

    def clean(self):
        if self.date_debut and self.date_fin and self.date_debut >= self.date_fin:
            raise ValidationError({"date_fin": "La date de fin doit être postérieure à la date de début."})

    def save(self, *args, **kwargs):
        self.libelle = self.libelle.strip()
        self.full_clean()
        if self.est_active:
            AnneeAcademique.objects.filter(est_active=True).exclude(pk=self.pk).update(est_active=False)
        super().save(*args, **kwargs)


class Classe(NamedDescriptionModel):
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="classes")
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE, related_name="classes")
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name="classes")
    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.PROTECT,
        related_name="classes_academique",
        db_index=True,
    )
    modules = models.ManyToManyField(Module, related_name="classes_academique", blank=True)
    nom = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["annee_academique__libelle", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["filiere", "niveau", "annee_academique"],
                name="unique_classe_per_filiere_niveau_annee",
            ),
        ]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        if not self.nom:
            self.nom = f"{self.filiere.nom} - {self.niveau.nom} ({self.annee_academique.libelle})"
        super().save(*args, **kwargs)

        if not self.modules.exists():
            base_modules = CourseAssignment.objects.filter(
                filiere=self.filiere,
                cycle=self.cycle,
                niveau=self.niveau,
            ).values_list("module_id", flat=True)
            if base_modules:
                self.modules.set(Module.objects.filter(id__in=base_modules))


class Semestre(NamedDescriptionModel):
    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.CASCADE,
        related_name="semestres_academique",
        db_index=True,
    )
    nom = models.CharField(max_length=100)
    ordre = models.PositiveIntegerField(default=1)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["annee_academique__libelle", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["annee_academique", "ordre"], name="unique_semestre_per_year_order_new"),
        ]

    def __str__(self):
        return f"{self.annee_academique.libelle} - {self.nom}"


class Evaluation(NamedDescriptionModel):
    TYPE_CHOICES = [
        ("CC", "CC"),
        ("EXAMEN", "Examen"),
        ("TP", "TP"),
        ("RATTRAPAGE", "Rattrapage"),
        ("AUTRE", "Autre"),
    ]

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="evaluations_academique")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="evaluations_academique")
    semestre = models.ForeignKey(
        Semestre,
        on_delete=models.SET_NULL,
        related_name="evaluations_academique",
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
                name="unique_evaluation_signature_academique",
            ),
        ]

    def __str__(self):
        return f"{self.libelle} - {self.classe.nom}"


class Affectation(TimeStampedModel):
    enseignant = models.ForeignKey(Formateur, on_delete=models.CASCADE, related_name="affectations_academique")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="affectations_academique")
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="affectations_academique")

    class Meta:
        ordering = ["classe__nom", "module__nom"]
        constraints = [
            models.UniqueConstraint(fields=["enseignant", "module", "classe"], name="unique_affectation_academique"),
        ]

    def __str__(self):
        return f"{self.enseignant.nom} - {self.module.nom} - {self.classe.nom}"


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
    cycle_souhaite = models.ForeignKey(
        Cycle, on_delete=models.SET_NULL, null=True, blank=True, related_name="pre_inscriptions"
    )
    niveau_souhaite = models.ForeignKey(
        Niveau, on_delete=models.SET_NULL, null=True, blank=True, related_name="pre_inscriptions"
    )
    annee_academique = models.ForeignKey(
        "AnneeAcademique", on_delete=models.SET_NULL, null=True, blank=True, related_name="pre_inscriptions"
    )
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default="EN_ATTENTE")
    bulletin = models.FileField(upload_to="pre_inscriptions/bulletins/", null=True, blank=True)
    message = models.TextField(blank=True)
    nom_parent = models.CharField(max_length=150, blank=True, verbose_name="Nom du parent")
    whatsapp_parent = models.CharField(max_length=20, blank=True, verbose_name="WhatsApp du parent")

    class Meta:
        ordering = ["-created_at"]

    @property
    def name(self):
        return f"{self.nom_candidat} {self.prenom_candidat}".strip()

    def __str__(self):
        return f"{self.nom_candidat} {self.prenom_candidat} - {self.statut}"


class Epreuve(NamedDescriptionModel):
    TYPE_CHOICES = [
        ("DEVOIR", "Devoir"),
        ("EXAMEN", "Examen"),
        ("RATTRAPAGE", "Rattrapage"),
        ("TP", "TP"),
        ("AUTRE", "Autre"),
    ]

    nom = models.CharField(max_length=255)
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="epreuves")
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name="epreuves")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="epreuves")
    annee_academique = models.ForeignKey(AnneeAcademique, on_delete=models.CASCADE, related_name="epreuves")
    semestre = models.ForeignKey(Semestre, on_delete=models.SET_NULL, null=True, blank=True, related_name="epreuves")
    type_epreuve = models.CharField(max_length=20, choices=TYPE_CHOICES, default="EXAMEN")

    # Fichiers
    fichier = models.FileField(upload_to="epreuves/sujets/")
    corrige = models.FileField(upload_to="epreuves/corriges/", null=True, blank=True, help_text="Corrigé ou barème optionnel")

    # Métadonnées et Droits d'Accès
    auteur = models.CharField(max_length=150, blank=True, help_text="Nom de l'enseignant ou concepteur")
    est_partage = models.BooleanField(default=True, help_text="Rendre visible par les étudiants")

    class Meta:
        ordering = ["-annee_academique__libelle", "filiere__nom", "niveau__nom", "module__nom", "nom"]

    def __str__(self):
        return f"{self.nom} - {self.module.nom} ({self.annee_academique.libelle})"


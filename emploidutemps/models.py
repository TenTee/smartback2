from django.db import models
from datetime import time
from formateurs.models import Formateur
from modules.models import Module
from academique.models import Filiere, Niveau
from django.core.exceptions import ValidationError
from django.db.models import Q


def periode_q(date_debut, date_fin):
    """Créneaux dont la période chevauche [date_debut, date_fin] (+ créneaux permanents, sans période)."""
    if not date_debut and not date_fin:
        return Q()
    q = Q(date_debut__isnull=True) | Q(date_fin__isnull=True)
    inner = Q()
    if date_fin:
        inner &= Q(date_debut__lte=date_fin)
    if date_debut:
        inner &= Q(date_fin__gte=date_debut)
    return q | inner


def semaine_de(jour):
    """Lundi et dimanche de la semaine contenant `jour`."""
    import datetime
    lundi = jour - datetime.timedelta(days=jour.weekday())
    return lundi, lundi + datetime.timedelta(days=6)

class Salle(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    capacite = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Salle"
        verbose_name_plural = "Salles"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

class EmploiDuTemps(models.Model):
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, null=True, blank=True)
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, null=True, blank=True)
    classe = models.ForeignKey("academique.Classe", on_delete=models.SET_NULL, null=True, blank=True, related_name="emplois_du_temps_academique")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    formateur = models.ForeignKey(Formateur, on_delete=models.CASCADE)
    jour = models.CharField(max_length=20)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    salle = models.ForeignKey(Salle, on_delete=models.CASCADE, related_name="emplois_du_temps")
    # Période de validité (ex. semaine du lundi 19/10/2026 au vendredi 23/10/2026).
    # Vide = créneau permanent (anciens emplois du temps).
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    # Tronc commun : même cours donné au même moment à plusieurs classes (même formateur, même salle).
    # Tous les créneaux du groupe partagent cet identifiant ; ils sont modifiés ensemble.
    tronc_commun = models.UUIDField(null=True, blank=True, db_index=True)

    def _hors_groupe(self, qs):
        """Exclut ce créneau et les autres classes de son tronc commun (qui partagent salle et formateur)."""
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if self.tronc_commun:
            qs = qs.exclude(tronc_commun=self.tronc_commun)
        return qs

    def clean(self):
        """Validation métier (admin/tests)."""
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError("La date de fin de période doit être postérieure à la date de début.")
        periode = periode_q(self.date_debut, self.date_fin)

        if self.classe_id:
            if self.filiere_id and self.classe.filiere_id != self.filiere_id:
                raise ValidationError("La classe fournie n'appartient pas à la filière sélectionnée.")
            if self.niveau_id and self.classe.niveau_id != self.niveau_id:
                raise ValidationError("La classe fournie n'appartient pas au niveau sélectionné.")

        # 1️⃣ Pause de la classe (ou du cycle) et amplitude de la journée
        from .horaires import erreur_horaires
        erreur = erreur_horaires(self.classe if self.classe_id else None, self.heure_debut, self.heure_fin)
        if erreur:
            raise ValidationError(erreur)

        # 1.2 Activités hors cours de la classe (ou utilisant la salle / le formateur)
        from .activites import message_conflit_cours
        msg = message_conflit_cours(self.classe_id, self.jour, self.heure_debut, self.heure_fin, self.date_debut, self.date_fin,
                                    self.salle_id, self.formateur_id)
        if msg:
            raise ValidationError(msg)

        # 2️⃣ Empêcher conflits de salle (hors classes du même tronc commun)
        conflits_salle = self._hors_groupe(EmploiDuTemps.objects.filter(periode).filter(
            jour=self.jour,
            salle=self.salle,
            heure_debut__lt=self.heure_fin,
            heure_fin__gt=self.heure_debut
        ))

        if conflits_salle.exists():
            raise ValidationError("⚠️ Conflit de salle : cette salle est déjà occupée à ce créneau.")

        # 3️⃣ Empêcher conflits de classe
        if self.classe_id:
            conflits_classe = EmploiDuTemps.objects.filter(periode).filter(
                jour=self.jour,
                classe=self.classe,
                heure_debut__lt=self.heure_fin,
                heure_fin__gt=self.heure_debut
            )

            if self.pk:
                conflits_classe = conflits_classe.exclude(pk=self.pk)

            if conflits_classe.exists():
                raise ValidationError("⚠️ Conflit de classe : cette classe a déjà un cours à ce créneau.")

        # 4️⃣ Empêcher conflits de formateur
        if self.formateur_id:
            conflits_formateur = self._hors_groupe(EmploiDuTemps.objects.filter(periode).filter(
                jour=self.jour,
                formateur=self.formateur,
                heure_debut__lt=self.heure_fin,
                heure_fin__gt=self.heure_debut
            ))

            if conflits_formateur.exists():
                raise ValidationError("⚠️ Conflit de formateur : ce formateur a déjà un cours à ce créneau.")

    def save(self, *args, **kwargs):
        """Sauvegarde + propagation directe des tronc communs."""
        if self.classe_id:
            self.niveau = self.classe.niveau
            self.filiere = self.classe.filiere
        self.full_clean()
        super().save(*args, **kwargs)

        # Logic for tronc commun duplication could be kept or adjusted
        # For now, I'll simplify as the original logic used Module.formations
        # and Module doesn't have a direct link to Filieres in the new system yet (only through CourseAssignment)

    def delete(self, *args, **kwargs):
        """Supprime ce créneau uniquement (pour tout le tronc commun : voir la vue, ?tout_le_tronc_commun=1)."""
        groupe = self.tronc_commun
        resultat = super().delete(*args, **kwargs)
        if groupe:
            restants = EmploiDuTemps.objects.filter(tronc_commun=groupe)
            if restants.count() == 1:  # une seule classe : ce n'est plus un tronc commun
                restants.update(tronc_commun=None)
        return resultat

    def __str__(self):
        return f"{self.filiere} | {self.jour} {self.heure_debut}-{self.heure_fin} | {self.module} ({self.formateur})"


class SeanceRealisee(models.Model):
    """Validation d'une séance (occurrence datée d'un créneau d'emploi du temps).

    Seules les séances validées « effectuée » sont comptées comme heures dispensées.
    Les informations du créneau sont recopiées pour garder l'historique si le créneau
    est ensuite modifié ou supprimé.
    """

    EFFECTUEE = "effectuee"
    NON_EFFECTUEE = "non_effectuee"
    STATUTS = [(EFFECTUEE, "Effectuée"), (NON_EFFECTUEE, "Non effectuée")]

    emploi = models.ForeignKey(EmploiDuTemps, on_delete=models.SET_NULL, null=True, blank=True, related_name="seances")
    date = models.DateField()
    statut = models.CharField(max_length=20, choices=STATUTS)
    formateur = models.ForeignKey(Formateur, on_delete=models.CASCADE, related_name="seances_realisees")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="seances_realisees")
    classe = models.ForeignKey("academique.Classe", on_delete=models.SET_NULL, null=True, blank=True, related_name="seances_realisees")
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    duree_minutes = models.PositiveIntegerField(default=0, help_text="Durée réellement effectuée (minutes)")
    commentaire = models.TextField(blank=True, default="")
    valide_par = models.ForeignKey("users.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="seances_validees")
    valide_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "heure_debut"]
        constraints = [models.UniqueConstraint(fields=["emploi", "date"], name="unique_seance_par_creneau_et_date")]

    def __str__(self):
        return f"{self.date} {self.module} ({self.get_statut_display()})"


class ActiviteClasse(models.Model):
    """Activité hors cours d'une ou plusieurs classes (sport, sortie, conférence, évaluation…).

    Ponctuelle : date_debut = date_fin (le jour de la semaine est déduit).
    Récurrente : chaque `jour` entre date_debut et date_fin.
    Elle occupe l'emploi du temps des classes : aucun cours ne peut être programmé au même moment.
    """

    TYPES = [
        ("sport", "Sport"),
        ("culture", "Activité culturelle"),
        ("club", "Club"),
        ("sortie", "Sortie / excursion"),
        ("visite", "Visite d'entreprise"),
        ("conference", "Conférence"),
        ("reunion", "Réunion"),
        ("ceremonie", "Cérémonie"),
        ("evaluation", "Évaluation / examen"),
        ("devoir", "Devoir surveillé"),
        ("autre", "Autre activité"),
    ]
    COULEURS = {
        "sport": "#2E7D32", "culture": "#8E24AA", "club": "#00838F", "sortie": "#EF6C00", "visite": "#F57C00",
        "conference": "#1565C0", "reunion": "#455A64", "ceremonie": "#AD1457", "evaluation": "#C62828",
        "devoir": "#D84315", "autre": "#6D4C41",
    }

    titre = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPES, default="autre")
    description = models.TextField(blank=True, default="")
    classes = models.ManyToManyField("academique.Classe", related_name="activites", blank=True)
    # Toutes les classes de l'année (y compris celles créées après l'activité)
    toutes_les_classes = models.BooleanField(default=False)
    annee_academique = models.ForeignKey("academique.AnneeAcademique", on_delete=models.CASCADE, null=True, blank=True, related_name="activites")
    recurrente = models.BooleanField(default=False)
    jour = models.CharField(max_length=20)
    date_debut = models.DateField()
    date_fin = models.DateField()
    journee_entiere = models.BooleanField(default=False)
    heure_debut = models.TimeField(null=True, blank=True)
    heure_fin = models.TimeField(null=True, blank=True)
    salle = models.ForeignKey(Salle, on_delete=models.SET_NULL, null=True, blank=True, related_name="activites")
    lieu = models.CharField(max_length=200, blank=True, default="", help_text="Lieu hors établissement (sortie, visite…)")
    formateur = models.ForeignKey(Formateur, on_delete=models.SET_NULL, null=True, blank=True, related_name="activites")
    responsable = models.CharField(max_length=200, blank=True, default="", help_text="Responsable / intervenant (si ce n'est pas un formateur)")
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="activites")
    obligatoire = models.BooleanField(default=True)
    cree_par = models.ForeignKey("users.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="activites_creees")
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date_debut", "heure_debut", "id"]
        verbose_name = "Activité de classe"
        verbose_name_plural = "Activités de classe"

    def __str__(self):
        return f"{self.titre} ({self.date_debut})"

    @property
    def couleur(self):
        return self.COULEURS.get(self.type, "#6D4C41")

    def classes_effectives(self):
        from academique.models import Classe
        if self.toutes_les_classes:
            return Classe.objects.filter(annee_academique_id=self.annee_academique_id) if self.annee_academique_id else Classe.objects.none()
        return self.classes.all()

    def plage(self):
        """Heures occupées (journée entière = toute la journée)."""
        if self.journee_entiere or not self.heure_debut or not self.heure_fin:
            return time(0, 0), time(23, 59)
        return self.heure_debut, self.heure_fin

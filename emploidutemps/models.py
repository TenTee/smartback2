from django.db import models
from datetime import time
from formateurs.models import Formateur
from modules.models import Module
from formations.models import Formation, Niveau
from django.core.exceptions import ValidationError

class EmploiDuTemps(models.Model):
    formation = models.ForeignKey(Formation, on_delete=models.CASCADE)
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, null=True, blank=True)
    classe = models.ForeignKey("academique.Classe", on_delete=models.SET_NULL, null=True, blank=True, related_name="emplois_du_temps")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    formateur = models.ForeignKey(Formateur, on_delete=models.CASCADE)
    jour = models.CharField(max_length=20)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    salle = models.CharField(max_length=100)

    def clean(self):
        """Validation métier (admin/tests)."""

        if self.classe_id:
            if self.formation_id and self.classe.niveau.formation_id != self.formation_id:
                raise ValidationError("La classe fournie n'appartient pas à la formation sélectionnée.")
            if self.niveau_id and self.classe.niveau_id != self.niveau_id:
                raise ValidationError("La classe fournie n'appartient pas au niveau sélectionné.")
            if not self.classe.modules.filter(pk=self.module_id).exists():
                raise ValidationError("Le module doit appartenir à la classe sélectionnée.")

        # 1️⃣ Bloquer la pause commune
        pause_debut = time(12, 0)
        pause_fin = time(13, 0)
        if self.heure_debut < pause_fin and self.heure_fin > pause_debut:
            raise ValidationError("⏸️ Impossible de programmer une séance pendant la pause déjeuner (12h00–13h00).")

        # 2️⃣ Empêcher conflits de salle (hors tronc communs du même module)
        conflits_salle = EmploiDuTemps.objects.filter(
            jour=self.jour,
            salle=self.salle,
            heure_debut__lt=self.heure_fin,
            heure_fin__gt=self.heure_debut
        ).exclude(module=self.module)

        if self.pk:
            conflits_salle = conflits_salle.exclude(pk=self.pk)

        if conflits_salle.exists():
            raise ValidationError("⚠️ Conflit de salle : cette salle est déjà occupée à ce créneau.")

        # 3️⃣ Empêcher conflits globaux (hors tronc communs du même module)
        conflits_horaire = EmploiDuTemps.objects.filter(
            jour=self.jour,
            heure_debut__lt=self.heure_fin,
            heure_fin__gt=self.heure_debut
        ).exclude(module=self.module)

        if self.pk:
            conflits_horaire = conflits_horaire.exclude(pk=self.pk)

        if conflits_horaire.exists():
            raise ValidationError("⚠️ Conflit détecté : une autre séance est déjà programmée à ce créneau.")

    def save(self, *args, **kwargs):
        """Sauvegarde + propagation directe des tronc communs."""
        if self.classe_id:
            self.niveau = self.classe.niveau
            self.formation = self.classe.niveau.formation
        self.full_clean()
        super().save(*args, **kwargs)

        # ⚡ Mettre à jour toutes les séances tronc communs du même module/créneau
        autres_seances = EmploiDuTemps.objects.filter(
            module=self.module,
            jour=self.jour,
            heure_debut=self.heure_debut,
            heure_fin=self.heure_fin
        ).exclude(pk=self.pk)

        for seance in autres_seances:
            seance.salle = self.salle
            seance.formateur = self.formateur
            super(EmploiDuTemps, seance).save()  # bypass full_clean pour éviter faux conflits

        # ⚡ Créer les duplications manquantes
        autres_formations = self.module.formations.exclude(pk=self.formation.pk)
        for formation in autres_formations:
            existe = EmploiDuTemps.objects.filter(
                formation=formation,
                module=self.module,
                jour=self.jour,
                heure_debut=self.heure_debut,
                heure_fin=self.heure_fin,
                salle=self.salle
            ).first()
            if not existe:
                EmploiDuTemps.objects.create(
                    formation=formation,
                    module=self.module,
                    jour=self.jour,
                    heure_debut=self.heure_debut,
                    heure_fin=self.heure_fin,
                    salle=self.salle,
                    formateur=self.formateur
                )

    def delete(self, *args, **kwargs):
        """Suppression synchronisée des tronc communs."""
        EmploiDuTemps.objects.filter(
            module=self.module,
            jour=self.jour,
            heure_debut=self.heure_debut,
            heure_fin=self.heure_fin
        ).delete()

    def __str__(self):
        return f"{self.formation} | {self.jour} {self.heure_debut}-{self.heure_fin} | {self.module} ({self.formateur})"

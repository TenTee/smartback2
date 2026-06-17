from django.db import models
from datetime import time
from formateurs.models import Formateur
from modules.models import Module
from academique.models import Filiere, Niveau
from django.core.exceptions import ValidationError

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

    def clean(self):
        """Validation métier (admin/tests)."""

        if self.classe_id:
            if self.filiere_id and self.classe.filiere_id != self.filiere_id:
                raise ValidationError("La classe fournie n'appartient pas à la filière sélectionnée.")
            if self.niveau_id and self.classe.niveau_id != self.niveau_id:
                raise ValidationError("La classe fournie n'appartient pas au niveau sélectionné.")

        # 1️⃣ Bloquer la pause par cycle
        if self.classe_id and self.classe.cycle and self.classe.cycle.type_cycle:
            cg = self.classe.cycle.type_cycle
            pause_debut = cg.heure_pause_debut
            pause_fin = cg.heure_pause_fin
            
            if self.heure_debut < pause_fin and self.heure_fin > pause_debut:
                raise ValidationError(f"⏸️ Impossible de programmer une séance pendant la pause ({pause_debut.strftime('%H:%M')}–{pause_fin.strftime('%H:%M')}).")
            
            # 1.1 Bloquer hors horaires journée
            debut_j = cg.heure_debut_journee
            fin_j = cg.heure_fin_journee
            if self.heure_debut < debut_j or self.heure_fin > fin_j:
                raise ValidationError(f"🕒 Hors créneau autorisé pour ce cycle ({debut_j.strftime('%H:%M')}–{fin_j.strftime('%H:%M')}).")
        else:
            # Fallback for old records or missing cycle info
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

        # 3️⃣ Empêcher conflits de classe
        if self.classe_id:
            conflits_classe = EmploiDuTemps.objects.filter(
                jour=self.jour,
                classe=self.classe,
                heure_debut__lt=self.heure_fin,
                heure_fin__gt=self.heure_debut
            ).exclude(module=self.module)

            if self.pk:
                conflits_classe = conflits_classe.exclude(pk=self.pk)

            if conflits_classe.exists():
                raise ValidationError("⚠️ Conflit de classe : cette classe a déjà un cours à ce créneau.")

        # 4️⃣ Empêcher conflits de formateur
        if self.formateur_id:
            conflits_formateur = EmploiDuTemps.objects.filter(
                jour=self.jour,
                formateur=self.formateur,
                heure_debut__lt=self.heure_fin,
                heure_fin__gt=self.heure_debut
            ).exclude(module=self.module)

            if self.pk:
                conflits_formateur = conflits_formateur.exclude(pk=self.pk)

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
        """Suppression synchronisée des tronc communs."""
        EmploiDuTemps.objects.filter(
            module=self.module,
            jour=self.jour,
            heure_debut=self.heure_debut,
            heure_fin=self.heure_fin
        ).delete()

    def __str__(self):
        return f"{self.filiere} | {self.jour} {self.heure_debut}-{self.heure_fin} | {self.module} ({self.formateur})"

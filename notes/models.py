# notes/models.py
from django.db import models
from etudiants.models import Etudiant
from modules.models import Module

class Note(models.Model):
    SESSION_CHOICES = [
        ("Semestre 1", "Semestre 1"),
        ("Semestre 2", "Semestre 2"),
    ]

    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="notes")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="notes")
    classe = models.ForeignKey(
        "academique.Classe",
        on_delete=models.SET_NULL,
        related_name="notes",
        null=True,
        blank=True,
    )
    evaluation = models.ForeignKey(
        "academique.Evaluation",
        on_delete=models.SET_NULL,
        related_name="notes",
        null=True,
        blank=True,
    )
    session = models.CharField(max_length=20, choices=SESSION_CHOICES)
    annee_academique = models.CharField(max_length=9, default="2024-2025")

    # ✅ Notes
    note_cc = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Note CC sur 20")
    note_sn = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Note SN sur 20")
    note_tp = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Note TP sur 20 (si applicable)")
    note_rattrapage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Note Rattrapage sur 20 (facultatif)")

    # ✅ Calcul automatique
    note_finale = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Note finale sur 20")

    def save(self, *args, **kwargs):
        """
        Calcul automatique pondéré de la note finale (sur 20) à partir des notes sur 20.
        note_finale = (cc*%cc + sn_ou_rattrapage*%sn [+ tp*%tp]) / 100
        - Si rattrapage existe → SN remplacée par rattrapage
        """
        if self.evaluation_id:
            self.module = self.evaluation.module
            self.classe = self.evaluation.classe
            if self.evaluation.semestre_id:
                self.session = self.evaluation.semestre.nom
                self.annee_academique = self.evaluation.semestre.annee_academique.libelle
            else:
                self.annee_academique = self.evaluation.classe.annee_academique.libelle
        elif self.module_id:
            self.session = self.module.semestre

        m = self.module
        if m and self.note_cc is not None:
            pc = getattr(m, "pourcentage_cc", 0) or 0
            psn = getattr(m, "pourcentage_sn", 0) or 0
            ptp = getattr(m, "pourcentage_tp", 0) or 0
            use_tp = getattr(m, "has_tp", False) and (self.note_tp is not None)
            sn_or_r = self.note_rattrapage if self.note_rattrapage is not None else self.note_sn
            total = (float(self.note_cc) * pc) + (float(sn_or_r or 0) * psn)
            if use_tp:
                total += float(self.note_tp) * ptp
            # Conversion sur 20
            self.note_finale = round(total / 100.0, 2)
        super().save(*args, **kwargs)

    @property
    def note_sur_20(self):
        """Retourne la note finale (déjà sur 20)"""
        return float(self.note_finale) if self.note_finale is not None else None

    @property
    def besoin_rattrapage(self):
        """Retourne True si la moyenne est < 9/20"""
        n20 = self.note_sur_20
        return (n20 is not None) and (n20 < 9)

    # ✅ Méthodes globales pour un étudiant
    @classmethod
    def moyenne_etudiant(cls, etudiant, session=None):
        """
        Calcule la moyenne générale pondérée par coefficients (sur 20).
        - Si session est précisée → moyenne pour ce semestre uniquement.
        - Sinon → moyenne sur toutes les notes.
        """
        notes = cls.objects.filter(etudiant=etudiant).select_related("module")
        if session:
            notes = notes.filter(session=session)

        total_coeff = 0
        total_points = 0.0
        for n in notes:
            if n.note_finale is not None and n.module is not None:
                coeff = getattr(n.module, "coefficient", 1) or 1
                total_coeff += coeff
                total_points += float(n.note_finale) * coeff

        if total_coeff == 0:
            return None  # aucune note saisie

        return round(total_points / total_coeff, 2)

    @classmethod
    def mention_etudiant(cls, etudiant, session=None):
        """
        Détermine la mention globale d'un étudiant selon sa moyenne.
        """
        moyenne = cls.moyenne_etudiant(etudiant, session=session)
        if moyenne is None:
            return "--"  # pas encore de notes

        if moyenne < 10:
            return "Échec"
        elif 10 <= moyenne < 12:
            return "Passable"
        elif 12 <= moyenne < 14:
            return "Assez Bien"
        elif 14 <= moyenne < 16:
            return "Bien"
        else:
            return "Très Bien"

    def __str__(self):
        return f"{self.etudiant.nom} - {self.module.nom} ({self.session}) : {self.note_finale or '--'}"

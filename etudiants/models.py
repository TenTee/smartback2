# etudiants/models.py
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from academique.models import Filiere, Niveau
from revenus.models import Revenu  

class Etudiant(models.Model):
    STATUT_CHOICES = (
        ('Pré-inscrit', 'Pré-inscrit'),
        ('Inscrit', 'Inscrit'),
    )
    matricule = models.CharField(max_length=30, unique=True, blank=True)
    nom = models.CharField(max_length=100)
    contact = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    date_naissance = models.DateField(null=True, blank=True)
    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name="etudiants")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='Pré-inscrit')
    
    def save(self, *args, **kwargs):
        # Génération automatique du matricule
        if not self.matricule:
            filiere_code = "ETUD"
            if self.filiere_id:
                filiere_code = self.filiere.nom[:4].upper()
            
            annee = timezone.now().year
            count = Etudiant.objects.filter(
                filiere=self.filiere,
                matricule__contains=str(annee)
            ).count() + 1
            self.matricule = f"{filiere_code}-{annee}-{count:04d}"

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.nom} - {self.matricule}"


class Inscription(models.Model):
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="inscriptions")
    classe = models.ForeignKey(
        "academique.Classe",
        on_delete=models.SET_NULL,
        related_name="inscriptions_detail",
        null=True,
        blank=True,
    )
    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name="inscriptions")
    annee_academique = models.CharField(max_length=15, help_text="Ex: 2024-2025")
    annee_academique_ref = models.ForeignKey(
        "academique.AnneeAcademique",
        on_delete=models.SET_NULL,
        related_name="inscriptions_academique",
        null=True,
        blank=True,
    )
    date_inscription = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('etudiant', 'niveau', 'annee_academique')
        constraints = [
            models.UniqueConstraint(
                fields=["etudiant", "classe", "annee_academique_ref"],
                name="unique_inscription_per_student_class_year_new",
            )
        ]

    def clean(self):
        if self.classe_id:
            if self.niveau_id and self.classe.niveau_id != self.niveau_id:
                raise ValidationError("La classe sélectionnée n'est pas cohérente avec le niveau fourni.")
            if self.annee_academique_ref_id and self.classe.annee_academique_id != self.annee_academique_ref_id:
                raise ValidationError("La classe sélectionnée n'appartient pas à l'année académique fournie.")

    def save(self, *args, **kwargs):
        if self.classe_id:
            self.niveau = self.classe.niveau
            self.annee_academique_ref = self.classe.annee_academique
            self.annee_academique = self.classe.annee_academique.libelle
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        label = self.classe.nom if self.classe_id else self.niveau.nom
        return f"{self.etudiant.nom} - {label} ({self.annee_academique})"


class EtudiantDocument(models.Model):
    etudiant = models.ForeignKey("Etudiant", on_delete=models.CASCADE, related_name="documents")
    fichier = models.FileField(upload_to="etudiants/documents/")
    type_document = models.CharField(max_length=50, blank=True, null=True)  # ex: "Photo", "Diplôme", "Attestation"
    date_upload = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.etudiant.nom} - {self.type_document or 'Document'}"

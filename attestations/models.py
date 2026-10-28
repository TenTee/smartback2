import secrets

from django.conf import settings
from django.db import models


def nouveau_code():
    return secrets.token_hex(8)  # 16 caractères, imprévisible : sert à la vérification par QR code


class DocumentDelivre(models.Model):
    """Registre des certificats de scolarité et cartes d'étudiant délivrés."""

    CERTIFICAT, CARTE, RELEVE = "certificat", "carte", "releve"
    TYPES = [(CERTIFICAT, "Certificat de scolarité"), (CARTE, "Carte d'étudiant"), (RELEVE, "Relevé de notes")]
    CANAUX = [("administration", "Administration"), ("portail", "Portail étudiant")]

    type = models.CharField(max_length=20, choices=TYPES)
    numero = models.CharField(max_length=60, unique=True)
    sequence = models.PositiveIntegerField()
    code = models.CharField(max_length=32, unique=True, default=nouveau_code)
    etudiant = models.ForeignKey("etudiants.Etudiant", on_delete=models.CASCADE, related_name="documents_delivres")
    inscription = models.ForeignKey("etudiants.Inscription", on_delete=models.SET_NULL, null=True, blank=True, related_name="documents_delivres")
    classe = models.ForeignKey("academique.Classe", on_delete=models.SET_NULL, null=True, blank=True, related_name="documents_delivres")
    annee_academique = models.ForeignKey("academique.AnneeAcademique", on_delete=models.SET_NULL, null=True, blank=True, related_name="documents_delivres")
    donnees = models.JSONField(default=dict, blank=True, help_text="Informations imprimées sur le document (figées à la délivrance)")
    delivre_le = models.DateTimeField(auto_now_add=True)
    delivre_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents_delivres")
    canal = models.CharField(max_length=20, choices=CANAUX, default="administration")
    valide_jusqu_au = models.DateField(null=True, blank=True)
    nb_impressions = models.PositiveIntegerField(default=1)
    derniere_impression = models.DateTimeField(null=True, blank=True)
    annule = models.BooleanField(default=False)
    annule_le = models.DateTimeField(null=True, blank=True)
    annule_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents_annules")
    motif_annulation = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-delivre_le", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["type", "annee_academique", "sequence"], name="unique_sequence_document_annee"),
        ]
        indexes = [models.Index(fields=["etudiant", "type", "annee_academique"])]

    def __str__(self):
        return f"{self.get_type_display()} {self.numero}"

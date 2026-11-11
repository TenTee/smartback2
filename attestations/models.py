import secrets

from django.conf import settings
from django.db import models


def nouveau_code():
    return secrets.token_hex(8)  # 16 caractères, imprévisible : sert à la vérification par QR code


class DocumentDelivre(models.Model):
    """Registre des certificats de scolarité et cartes d'étudiant délivrés."""

    CERTIFICAT, CARTE, RELEVE, REUSSITE = "certificat", "carte", "releve", "reussite"
    TYPES = [(CERTIFICAT, "Certificat de scolarité"), (CARTE, "Carte d'étudiant"), (RELEVE, "Relevé de notes"),
             (REUSSITE, "Attestation de réussite professionnelle")]
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


class DemandeDocument(models.Model):
    """Demande d'un document officiel par un étudiant depuis son portail.

    L'étudiant ne télécharge plus lui-même ses documents : il en fait la demande, l'administration
    le génère, l'imprime et le lui remet (en attente → prêt à retirer → remis, ou rejeté).
    """

    EN_ATTENTE, PRETE, REMISE, REJETEE = "en_attente", "prete", "remise", "rejetee"
    STATUTS = [(EN_ATTENTE, "En attente"), (PRETE, "Prêt à retirer"), (REMISE, "Remis"), (REJETEE, "Rejetée")]
    TYPES = [(DocumentDelivre.CERTIFICAT, "Certificat de scolarité"), (DocumentDelivre.RELEVE, "Relevé de notes"),
             (DocumentDelivre.CARTE, "Carte d'étudiant")]

    reference = models.CharField(max_length=30, unique=True, editable=False)
    etudiant = models.ForeignKey("etudiants.Etudiant", on_delete=models.CASCADE, related_name="demandes_documents")
    annee_academique = models.ForeignKey("academique.AnneeAcademique", on_delete=models.SET_NULL, null=True, blank=True, related_name="demandes_documents")
    type = models.CharField(max_length=20, choices=TYPES)
    nombre = models.PositiveSmallIntegerField(default=1, help_text="Nombre d'exemplaires")
    motif = models.CharField(max_length=255, blank=True, default="", help_text="Usage prévu (banque, stage, visa…)")
    statut = models.CharField(max_length=20, choices=STATUTS, default=EN_ATTENTE)
    reponse = models.CharField(max_length=255, blank=True, default="", help_text="Message de l'administration (motif de rejet, consignes de retrait…)")
    document = models.ForeignKey(DocumentDelivre, on_delete=models.SET_NULL, null=True, blank=True, related_name="demandes")
    cree_le = models.DateTimeField(auto_now_add=True)
    traite_le = models.DateTimeField(null=True, blank=True)
    traite_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="demandes_documents_traitees")
    remise_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le", "-id"]
        indexes = [models.Index(fields=["statut", "type"])]

    def save(self, *args, **kwargs):
        if not self.reference:
            from django.utils import timezone
            base = f"DOC-{timezone.localdate():%Y%m}-"
            n = DemandeDocument.objects.filter(reference__startswith=base).count() + 1
            while DemandeDocument.objects.filter(reference=f"{base}{n:04d}").exists():
                n += 1
            self.reference = f"{base}{n:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} — {self.get_type_display()}"

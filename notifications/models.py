from django.conf import settings
from django.db import models


class Notification(models.Model):
    CATEGORIES = [
        ("finance", "Finances"),
        ("etudiants", "Étudiants"),
        ("pedagogie", "Pédagogie"),
        ("etudiant", "Ma scolarité"),
        ("enseignement", "Mes cours"),
        ("messages", "Messages"),
        ("systeme", "Système"),
    ]
    NIVEAUX = [("info", "Information"), ("succes", "Succès"), ("alerte", "Alerte"), ("urgent", "Urgent")]

    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    categorie = models.CharField(max_length=20, choices=CATEGORIES)
    type = models.CharField(max_length=50, help_text="Code de l'événement, ex. paiement_recu")
    titre = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    lien = models.CharField(max_length=300, blank=True, default="", help_text="Page de l'application à ouvrir")
    niveau = models.CharField(max_length=10, choices=NIVEAUX, default="info")
    cle = models.CharField(max_length=150, blank=True, default="", help_text="Évite les doublons (rappels périodiques)")
    lu = models.BooleanField(default=False)
    lu_le = models.DateTimeField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["destinataire", "lu"]), models.Index(fields=["destinataire", "cle"])]

    def __str__(self):
        return f"{self.titre} → {self.destinataire}"


class AbonnementPush(models.Model):
    """Abonnement Web Push d'un navigateur / appareil."""

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="abonnements_push")
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    navigateur = models.CharField(max_length=255, blank=True, default="")
    cree_le = models.DateTimeField(auto_now_add=True)
    dernier_envoi = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Push {self.utilisateur} ({self.navigateur[:30]})"


class PreferenceNotification(models.Model):
    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preference_notifications")
    categories_desactivees = models.JSONField(default=list, blank=True)
    push_actif = models.BooleanField(default=True)

    def __str__(self):
        return f"Préférences de {self.utilisateur}"


class ClesPush(models.Model):
    """Clés Web Push (VAPID) créées automatiquement par le serveur : aucune configuration à faire."""

    cle_publique = models.CharField(max_length=200)
    cle_privee = models.CharField(max_length=200)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Clés de notifications push"

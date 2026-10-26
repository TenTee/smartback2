import os

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """Fil de discussion.

    - « service » : un étudiant et un service de l'établissement (scolarité, finances, pédagogie) ;
    - « classe »  : une classe et un module — le(s) formateur(s) du module et les étudiants de la classe.
    """

    SERVICE, CLASSE = "service", "classe"
    TYPES = [(SERVICE, "Étudiant ↔ service"), (CLASSE, "Classe ↔ formateur")]
    SERVICES = [("scolarite", "Scolarité"), ("finance", "Service financier"), ("pedagogie", "Pédagogie")]

    type = models.CharField(max_length=10, choices=TYPES)
    service = models.CharField(max_length=20, choices=SERVICES, blank=True, default="")
    etudiant = models.ForeignKey("etudiants.Etudiant", on_delete=models.CASCADE, null=True, blank=True, related_name="conversations")
    classe = models.ForeignKey("academique.Classe", on_delete=models.CASCADE, null=True, blank=True, related_name="conversations")
    module = models.ForeignKey("modules.Module", on_delete=models.CASCADE, null=True, blank=True, related_name="conversations")
    cree_le = models.DateTimeField(auto_now_add=True)
    dernier_message_le = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-dernier_message_le", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["etudiant", "service"], condition=models.Q(type="service"), name="unique_conversation_service"),
            models.UniqueConstraint(fields=["classe", "module"], condition=models.Q(type="classe"), name="unique_conversation_classe"),
        ]

    def __str__(self):
        if self.type == self.SERVICE:
            return f"{self.get_service_display()} — {getattr(self.etudiant, 'nom', '')}"
        return f"{getattr(self.classe, 'nom', '')} — {getattr(self.module, 'nom', '')}"


def chemin_piece_jointe(instance, filename):
    return f"messagerie/{instance.conversation_id}/{os.path.basename(filename)}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="messages_envoyes")
    texte = models.TextField(blank=True, default="")
    piece_jointe = models.FileField(upload_to=chemin_piece_jointe, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Lecture(models.Model):
    """Dernier message lu par un utilisateur dans une conversation."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="lectures")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lectures_messagerie")
    dernier_lu = models.PositiveBigIntegerField(default=0)
    lu_le = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "utilisateur"], name="unique_lecture_conversation")]

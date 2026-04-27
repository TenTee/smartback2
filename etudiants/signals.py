from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Etudiant
from notes.models import Note

@receiver(post_save, sender=Etudiant)
def create_or_update_notes(sender, instance, created, **kwargs):
    """
    ✅ Lorsqu'un étudiant est ajouté ou modifié :
    - Création automatique de ses notes vides en Semestre 1
    - Mise à jour si besoin (ajout/suppression selon la filière)
    """
    if instance.statut == 'Pré-inscrit':
        # Ne pas générer de notes tant que l'inscription n'est pas validée
        return

    current_modules = set(instance.filiere.modules.all())
    existing_notes = Note.objects.filter(etudiant=instance, session="Semestre 1")

    if created:
        # Créer une note vide pour chaque module de sa filière
        for module in current_modules:
            Note.objects.get_or_create(
                etudiant=instance,
                module=module,
                session="Semestre 1",
                defaults={
                    "note_cc": None,
                    "note_sn": None,
                    "note_rattrapage": None,
                    "note_finale": None,
                }
            )
    else:
        # Supprimer les notes des modules qui ne sont plus dans la filière
        for note in existing_notes:
            if note.module not in current_modules:
                note.delete()

        # Créer les notes manquantes pour les nouveaux modules
        for module in current_modules:
            Note.objects.get_or_create(
                etudiant=instance,
                module=module,
                session="Semestre 1"
            )

@receiver(post_delete, sender=Etudiant)
def delete_notes(sender, instance, **kwargs):
    """
    ✅ Lorsqu'un étudiant est supprimé :
    - Supprimer toutes ses notes
    """
    Note.objects.filter(etudiant=instance).delete()
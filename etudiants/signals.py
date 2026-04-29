from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Etudiant, Inscription
from notes.models import Note

@receiver(post_save, sender=Inscription)
def create_or_update_notes_on_inscription(sender, instance, created, **kwargs):
    """
    ✅ Lorsqu'une inscription est ajoutée ou modifiée :
    - Génération des notes basées sur les modules de la CLASSE
    """
    if not instance.classe:
        return

    # Modules de la classe
    current_modules = set(instance.classe.modules.all())
    
    # Sessions à initialiser (on pourrait boucler sur les semestres si besoin)
    sessions = ["Semestre 1", "Semestre 2"] # Exemple simplifié

    for session in sessions:
        # Création des notes manquantes
        for module in current_modules:
            Note.objects.get_or_create(
                etudiant=instance.etudiant,
                module=module,
                classe=instance.classe, # Important: on lie à la classe
                session=session,
                defaults={
                    "note_cc": None,
                    "note_sn": None,
                    "note_rattrapage": None,
                    "note_finale": None,
                }
            )

    # Nettoyage facultatif : supprimer les notes si l'étudiant change de classe/modules ?
    # Pour l'instant on se concentre sur la création.

@receiver(post_delete, sender=Etudiant)
def delete_notes(sender, instance, **kwargs):
    """
    ✅ Lorsqu'un étudiant est supprimé :
    - Supprimer toutes ses notes
    """
    Note.objects.filter(etudiant=instance).delete()
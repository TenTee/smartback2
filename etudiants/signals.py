from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Etudiant, Inscription
from notes.models import Note
from users.models import CustomUser

@receiver(post_save, sender=Etudiant)
def create_user_for_etudiant(sender, instance, created, **kwargs):
    """
    ✅ Lorsqu'un étudiant est créé :
    - Création automatique d'un compte utilisateur (CustomUser)
    - Association du compte à l'étudiant
    - Stockage du mot de passe initial pour l'administrateur
    """
    if created and not instance.user:
        # Extraire nom et prénom (simplifié)
        parts = instance.nom.split(' ', 1)
        nom = parts[0]
        prenom = parts[1] if len(parts) > 1 else ""

        # Création de l'utilisateur
        user = CustomUser.objects.create(
            noms=nom,
            prenoms=prenom,
            email=instance.email,
            role="etudiant" # Rôle spécifique
        )
        
        # Récupération du mot de passe brut (généré dans le save() de CustomUser)
        raw_password = getattr(user, '_raw_password', None)
        
        # Mise à jour de l'étudiant
        instance.user = user
        instance.initial_password = raw_password
        instance.save(update_fields=['user', 'initial_password'])

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
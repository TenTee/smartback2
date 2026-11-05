from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Etudiant, Inscription
from notes.models import Note
from users.models import CustomUser

@receiver(post_save, sender=Etudiant)
def create_user_for_etudiant(sender, instance, created, **kwargs):
    """
    Lorsqu'un étudiant est créé :
    - Création automatique d'un compte utilisateur (CustomUser)
    - Association du compte à l'étudiant
    - Stockage du mot de passe initial pour l'administrateur
    """
    if created and not instance.user:
        parts = instance.nom.split(' ', 1)
        nom = parts[0]
        prenom = parts[1] if len(parts) > 1 else ""

        clean_email = (instance.email or "").strip().lower()
        existing_user = CustomUser.objects.filter(email__iexact=clean_email).first()

        if existing_user:
            user = existing_user
            raw_password = None
        else:
            user = CustomUser.objects.create(
                noms=nom,
                prenoms=prenom,
                email=clean_email,
                role="etudiant",
            )
            raw_password = getattr(user, '_raw_password', None)

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
    
    # Une ligne de note par module, dans le semestre du module
    for module in current_modules:
        creer_note_vide(instance.etudiant, module, instance.classe)


def creer_note_vide(etudiant, module, classe):
    """Ligne de note vide (à saisir) pour un module du programme, sauf si l'étudiant en a déjà une."""
    if Note.objects.filter(etudiant=etudiant, module=module, classe=classe).exists():
        return
    Note.objects.get_or_create(
        etudiant=etudiant, module=module, classe=classe, session=module.semestre or "Semestre 1",
        evaluation=None,
        defaults={"note_cc": None, "note_sn": None, "note_rattrapage": None, "note_finale": None},
    )


def _modules_ajoutes_a_la_classe(sender, instance, action, pk_set, **kwargs):
    """Module ajouté au programme d'une classe : lignes de notes pour tous les étudiants déjà inscrits."""
    if action != "post_add" or not pk_set:
        return
    from academique.models import Classe
    from modules.models import Module
    if not isinstance(instance, Classe):
        return
    modules = list(Module.objects.filter(pk__in=pk_set))
    for ins in Inscription.objects.filter(classe=instance).select_related("etudiant"):
        for module in modules:
            creer_note_vide(ins.etudiant, module, instance)


def _brancher_programme():
    from django.db.models.signals import m2m_changed
    from academique.models import Classe
    m2m_changed.connect(_modules_ajoutes_a_la_classe, sender=Classe.modules.through, dispatch_uid="notes_programme_classe")


_brancher_programme()

@receiver(post_delete, sender=Etudiant)
def delete_notes(sender, instance, **kwargs):
    """
    ✅ Lorsqu'un étudiant est supprimé :
    - Supprimer toutes ses notes
    """
    Note.objects.filter(etudiant=instance).delete()
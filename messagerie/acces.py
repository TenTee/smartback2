"""Qui voit quelle conversation, et qui est prévenu des nouveaux messages."""
from django.db.models import Q

from notifications.services import destinataires, droit, est_super_admin, profil

from .models import Conversation

# Service → domaine de droits du rôle
DOMAINE_SERVICE = {"scolarite": "etudiants", "finance": "finance", "pedagogie": "pedagogie"}


def annee_id():
    from academique.middleware import get_current_academic_year_id
    from academique.models import AnneeAcademique

    a = None
    try:
        a = get_current_academic_year_id()
    except Exception:  # noqa: BLE001
        a = None
    if not a:
        a = AnneeAcademique.objects.filter(est_active=True).values_list("id", flat=True).first()
    return a


def etudiant_de(user):
    try:
        return user.etudiant_profile
    except Exception:  # noqa: BLE001
        return None


def formateur_de(user):
    try:
        return user.formateur_profile
    except Exception:  # noqa: BLE001
        return None


def classe_courante(etudiant):
    from etudiants.models import Inscription

    qs = Inscription.objects.filter(etudiant=etudiant, classe__isnull=False).select_related("classe")
    a = annee_id()
    ins = (qs.filter(classe__annee_academique_id=a).first() if a else None) or qs.order_by("-id").first()
    return ins.classe if ins else None


def paires_formateur(formateur, a=None):
    """(classe, module) enseignés par le formateur : affectations + emplois du temps."""
    from academique.models import Affectation
    from emploidutemps.models import EmploiDuTemps

    a = a or annee_id()
    paires = set()
    aff = Affectation.objects.filter(enseignant=formateur)
    edt = EmploiDuTemps.objects.filter(formateur=formateur, classe__isnull=False)
    if a:
        aff, edt = aff.filter(classe__annee_academique_id=a), edt.filter(classe__annee_academique_id=a)
    paires |= set(aff.values_list("classe_id", "module_id"))
    paires |= set(edt.values_list("classe_id", "module_id"))
    return paires


def paires_classe(classe_id):
    """Modules enseignés dans une classe (avec au moins un formateur)."""
    from academique.models import Affectation
    from emploidutemps.models import EmploiDuTemps

    mods = set(Affectation.objects.filter(classe_id=classe_id).values_list("module_id", flat=True))
    mods |= set(EmploiDuTemps.objects.filter(classe_id=classe_id).values_list("module_id", flat=True))
    return {(classe_id, m) for m in mods}


def formateurs_de(classe_id, module_id):
    from academique.models import Affectation
    from emploidutemps.models import EmploiDuTemps
    from formateurs.models import Formateur

    ids = set(Affectation.objects.filter(classe_id=classe_id, module_id=module_id).values_list("enseignant_id", flat=True))
    ids |= set(EmploiDuTemps.objects.filter(classe_id=classe_id, module_id=module_id).values_list("formateur_id", flat=True))
    return Formateur.objects.filter(id__in=ids).select_related("user")


def services_accessibles(user):
    return [s for s, d in DOMAINE_SERVICE.items() if droit(user, d) != "none"]


def peut_acceder(user, conv):
    p = profil(user)
    if conv.type == Conversation.SERVICE:
        if p == "etudiant":
            return conv.etudiant_id == etudiant_de(user).id
        if p == "formateur":
            return False
        return conv.service in services_accessibles(user)
    # classe
    if p == "etudiant":
        from etudiants.models import Inscription
        return Inscription.objects.filter(etudiant=etudiant_de(user), classe_id=conv.classe_id).exists()
    if p == "formateur":
        return formateurs_de(conv.classe_id, conv.module_id).filter(pk=formateur_de(user).pk).exists()
    return est_super_admin(user) or droit(user, "pedagogie") != "none"


def conversations_visibles(user):
    """Conversations à afficher dans la liste (créées au besoin pour étudiants et formateurs)."""
    p = profil(user)
    if p == "etudiant":
        etu = etudiant_de(user)
        for s, _ in Conversation.SERVICES:
            Conversation.objects.get_or_create(type=Conversation.SERVICE, etudiant=etu, service=s)
        classe = classe_courante(etu)
        q = Q(type=Conversation.SERVICE, etudiant=etu)
        if classe:
            for c, m in paires_classe(classe.id):
                Conversation.objects.get_or_create(type=Conversation.CLASSE, classe_id=c, module_id=m)
            q |= Q(type=Conversation.CLASSE, classe=classe)
        return Conversation.objects.filter(q)
    if p == "formateur":
        paires = paires_formateur(formateur_de(user))
        q = Q(pk__in=[])
        for c, m in paires:
            Conversation.objects.get_or_create(type=Conversation.CLASSE, classe_id=c, module_id=m)
            q |= Q(type=Conversation.CLASSE, classe_id=c, module_id=m)
        return Conversation.objects.filter(q)
    # Personnel : seulement les fils déjà commencés (ou ouverts explicitement)
    services = services_accessibles(user)
    q = Q(type=Conversation.SERVICE, service__in=services)
    if est_super_admin(user) or droit(user, "pedagogie") != "none":
        a = annee_id()
        qc = Q(type=Conversation.CLASSE)
        if a:
            qc &= Q(classe__annee_academique_id=a)
        q |= qc
    return Conversation.objects.filter(q, dernier_message_le__isnull=False)


def a_prevenir(conv, auteur):
    """Comptes à notifier d'un nouveau message (jamais l'auteur)."""
    from users.models import CustomUser

    p = profil(auteur)
    users = []
    if conv.type == Conversation.SERVICE:
        if p == "etudiant":
            users = list(destinataires([DOMAINE_SERVICE[conv.service]]))
        elif conv.etudiant and conv.etudiant.user_id:
            users = [conv.etudiant.user]
    else:
        formateurs = [f.user for f in formateurs_de(conv.classe_id, conv.module_id) if f.user_id]
        if p == "etudiant":
            users = formateurs  # un message d'étudiant va au(x) formateur(s), pas à toute la classe
        else:
            etudiants = CustomUser.objects.filter(is_active=True, etudiant_profile__inscriptions__classe_id=conv.classe_id).distinct()
            users = formateurs + list(etudiants)
    return [u for u in users if u and u.pk != auteur.pk]

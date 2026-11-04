"""Droits d'accès à l'inventaire (droit « Logistique » du rôle) et notifications des responsables."""
from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission


def droit_logistique(user):
    from notifications.services import est_super_admin, profil
    if not user or not user.is_authenticated:
        return "none"
    if est_super_admin(user):
        return "ecriture"
    if profil(user) != "personnel":
        return "none"
    from users.models import Role
    return Role.objects.filter(code=user.role).values_list("can_manage_logistique", flat=True).first() or "none"


def peut_signaler(user):
    """Tout membre du personnel ou formateur peut consulter une fiche (scan) et signaler une panne."""
    from notifications.services import profil
    return bool(user and user.is_authenticated and profil(user) in ("personnel", "formateur"))


class DroitLogistique(BasePermission):
    """Lecture : personnel et formateurs. Écriture : droit Logistique en écriture."""
    message = "Votre rôle ne permet pas de modifier l'inventaire (droit Logistique)."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return peut_signaler(request.user)
        return droit_logistique(request.user) == "ecriture"


class LectureLogistique(BasePermission):
    """Lecture réservée aux utilisateurs ayant le droit Logistique (valeurs, tableaux de bord)."""
    message = "Votre rôle ne donne pas accès à l'inventaire."

    def has_permission(self, request, view):
        d = droit_logistique(request.user)
        return d != "none" if request.method in SAFE_METHODS else d == "ecriture"


def responsables_logistique():
    from notifications.services import ROLES_SUPER_ADMIN
    from users.models import CustomUser, Role
    codes = set(Role.objects.exclude(can_manage_logistique="none").values_list("code", flat=True))
    q = Q(is_superuser=True) | Q(role__in=codes)
    for r in ROLES_SUPER_ADMIN:
        q |= Q(role__iexact=r)
    return (CustomUser.objects.filter(is_active=True).filter(q)
            .exclude(etudiant_profile__isnull=False).exclude(formateur_profile__isnull=False).distinct())


def notifier_logistique(type_, titre, message="", lien="/inventory", niveau="info"):
    try:
        from notifications.services import notifier_utilisateurs
        notifier_utilisateurs(list(responsables_logistique()), "systeme", type_, titre, message, lien, niveau)
    except Exception:  # noqa: BLE001  — une notification ne doit jamais bloquer l'action
        import logging
        logging.getLogger(__name__).exception("Notification logistique impossible")

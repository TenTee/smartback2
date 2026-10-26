"""Envoi des notifications aux responsables concernés (application + Web Push)."""
import contextvars
import json
import logging
import threading

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Domaine de notification → droit du rôle donnant accès à ce domaine
DOMAINES = {
    "finance": "can_manage_finance",
    "etudiants": "can_manage_etudiants",
    "pedagogie": "can_manage_pedagogie",
}
ROLES_SUPER_ADMIN = {"admin", "administrateur", "adm", "super admin", "superadmin", "super-admin"}

# Requête en cours (pour ne pas notifier l'auteur de l'action)
_requete = contextvars.ContextVar("notifications_requete", default=None)


class RequeteCouranteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _requete.set(request)
        try:
            return self.get_response(request)
        finally:
            _requete.reset(token)


def auteur_courant():
    req = _requete.get()
    user = getattr(req, "user", None) if req is not None else None
    return user if user is not None and getattr(user, "is_authenticated", False) else None


def destinataires(domaines):
    """Responsables d'au moins un des domaines (droit ≠ « Aucun ») + super administrateurs."""
    from users.models import CustomUser, Role

    codes = set()
    for d in domaines:
        champ = DOMAINES.get(d)
        if champ:
            codes |= set(Role.objects.exclude(**{champ: "none"}).values_list("code", flat=True))
    q = Q(is_superuser=True) | Q(role__in=codes)
    for r in ROLES_SUPER_ADMIN:
        q |= Q(role__iexact=r)
    return (
        CustomUser.objects.filter(is_active=True)
        .filter(q)
        .exclude(etudiant_profile__isnull=False)
        .exclude(formateur_profile__isnull=False)
        .distinct()
    )


def profil(user):
    """« etudiant », « formateur » ou « personnel »."""
    if user is None:
        return None
    if _profil_existe(user, "etudiant_profile"):
        return "etudiant"
    if _profil_existe(user, "formateur_profile"):
        return "formateur"
    return "personnel"


def _profil_existe(user, attr):
    try:
        return getattr(user, attr, None) is not None
    except Exception:  # noqa: BLE001  (RelatedObjectDoesNotExist)
        return False


def est_super_admin(user):
    return bool(user and (user.is_superuser or str(getattr(user, "role", "") or "").strip().lower() in ROLES_SUPER_ADMIN))


def droit(user, domaine):
    """Droit du rôle de l'utilisateur sur un domaine : none / lecture / ecriture."""
    if est_super_admin(user):
        return "ecriture"
    champ = DOMAINES.get(domaine)
    if not champ or not getattr(user, "role", None):
        return "none"
    from users.models import Role
    r = Role.objects.filter(code=user.role).values_list(champ, flat=True).first()
    return r or "none"


def categories_utilisateur(user):
    """Catégories de notifications qu'un utilisateur peut recevoir (pour ses réglages)."""
    p = profil(user)
    if p == "etudiant":
        return ["etudiant", "messages"]
    if p == "formateur":
        return ["enseignement", "messages"]
    return [d for d in DOMAINES if droit(user, d) != "none"] + ["messages"]


def notifier(domaines, type, titre, message="", lien="", niveau="info", cle="", inclure_auteur=False):
    """Crée une notification pour chaque responsable concerné, puis envoie les push après validation.

    domaines : liste parmi DOMAINES (la 1re sert de catégorie)
    cle      : si renseignée, un responsable ne reçoit qu'une fois la notification portant cette clé
    """
    if isinstance(domaines, str):
        domaines = [domaines]
    return notifier_utilisateurs(
        list(destinataires(domaines)), domaines[0], type, titre, message, lien, niveau, cle, inclure_auteur,
    )


def comptes_portail(utilisateurs):
    """Garde les comptes actifs (étudiants, formateurs ou personnel) d'une liste / queryset."""
    return [u for u in utilisateurs if u is not None and getattr(u, "is_active", False)]


def notifier_utilisateurs(users, categorie, type, titre, message="", lien="", niveau="info", cle="", inclure_auteur=False):
    """Notifie des utilisateurs précis (étudiants, formateurs, personnel)."""
    from .models import Notification, PreferenceNotification

    auteur = None if inclure_auteur else auteur_courant()
    vus, uniques = set(), []
    for u in comptes_portail(users):
        if u.pk not in vus:
            vus.add(u.pk)
            uniques.append(u)
    users = uniques
    prefs = {p.utilisateur_id: p for p in PreferenceNotification.objects.filter(utilisateur__in=users)}
    deja = set()
    if cle:
        deja = set(Notification.objects.filter(cle=cle, destinataire__in=users).values_list("destinataire_id", flat=True))
    crees = []
    for u in users:
        if auteur is not None and u.pk == auteur.pk:
            continue
        if u.pk in deja:
            continue
        p = prefs.get(u.pk)
        if p and categorie in (p.categories_desactivees or []):
            continue
        crees.append(Notification(
            destinataire=u, categorie=categorie, type=type, titre=titre[:200], message=message,
            lien=lien[:300], niveau=niveau, cle=cle[:150],
        ))
    if not crees:
        return []
    Notification.objects.bulk_create(crees)
    payload = {"titre": titre, "message": message, "lien": lien, "niveau": niveau, "categorie": categorie}
    ids = [n.destinataire_id for n in crees if not (prefs.get(n.destinataire_id) and not prefs[n.destinataire_id].push_actif)]
    if ids:
        transaction.on_commit(lambda: _envoyer_push_async(ids, payload))
    return crees


# ---------------------------------------------------------------------------
# Web Push
# ---------------------------------------------------------------------------
def push_configure():
    return bool(getattr(settings, "VAPID_PUBLIC_KEY", "") and getattr(settings, "VAPID_PRIVATE_KEY", ""))


def _envoyer_push_async(user_ids, payload):
    if not push_configure():
        return
    threading.Thread(target=envoyer_push, args=(user_ids, payload), daemon=True).start()


def envoyer_push(user_ids, payload):
    """Envoie le push à tous les appareils abonnés des utilisateurs. Supprime les abonnements expirés."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush n'est pas installé : notifications push désactivées.")
        return 0
    from .models import AbonnementPush

    envoyes = 0
    data = json.dumps(payload)
    claims = {"sub": f"mailto:{getattr(settings, 'VAPID_EMAIL', '') or 'admin@example.com'}"}
    for ab in AbonnementPush.objects.filter(utilisateur_id__in=user_ids):
        try:
            webpush(
                subscription_info={"endpoint": ab.endpoint, "keys": {"p256dh": ab.p256dh, "auth": ab.auth}},
                data=data,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=dict(claims),
                ttl=86400,
            )
            AbonnementPush.objects.filter(pk=ab.pk).update(dernier_envoi=timezone.now())
            envoyes += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                ab.delete()  # abonnement expiré / révoqué par le navigateur
            else:
                logger.warning("Échec d'envoi push (%s) : %s", status, e)
        except Exception as e:  # noqa: BLE001
            logger.warning("Échec d'envoi push : %s", e)
    return envoyes

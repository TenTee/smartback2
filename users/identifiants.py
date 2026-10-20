"""Gestion commune des identifiants (étudiants, formateurs, personnel).

Le dernier mot de passe généré ou défini par l'administration est conservé sur le compte
(`mot_de_passe_provisoire`) pour pouvoir être communiqué à nouveau ; il est effacé dès que
l'utilisateur choisit son propre mot de passe depuis « Mon profil ».
"""
from django.utils import timezone
from django.utils.crypto import get_random_string

ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def est_admin(user):
    """Les comptes étudiant / formateur n'ont pas accès aux identifiants des autres."""
    return bool(user and user.is_authenticated and not hasattr(user, "etudiant_profile") and not hasattr(user, "formateur_profile"))


def generer_mot_de_passe(longueur=10):
    return get_random_string(longueur, allowed_chars=ALPHABET)


def nouvel_identifiant(noms, prenoms=""):
    from users.models import CustomUser
    base = ".".join(p for p in f"{noms} {prenoms}".lower().split() if p)[:40] or "utilisateur"
    while True:
        username = f"{base}{get_random_string(3, allowed_chars='0123456789')}"
        if not CustomUser.objects.filter(username=username).exists():
            return username


def infos(user, email_defaut=""):
    return {
        "a_un_compte": bool(user),
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "email": (user.email if user else None) or email_defaut,
        "mot_de_passe": user.mot_de_passe_provisoire if user else None,
        "mdp_modifie_par_utilisateur": bool(user and user.mdp_modifie_par_utilisateur),
        # compatibilité avec l'écran formateur existant
        "mdp_modifie_par_formateur": bool(user and user.mdp_modifie_par_utilisateur),
        "compte_actif": bool(user and user.is_active),
        "derniere_connexion": user.last_login if user else None,
        "identifiants_maj_le": user.identifiants_maj_le if user else None,
        "role": user.role if user else None,
    }


def reinitialiser(user, mot_de_passe=None, regenerer_identifiant=False):
    """Définit un nouveau mot de passe (généré si absent), réactive le compte. Renvoie le mot de passe."""
    from users.models import CustomUser
    mdp = mot_de_passe or generer_mot_de_passe()
    if regenerer_identifiant:
        username = nouvel_identifiant(user.noms, user.prenoms)
        CustomUser.objects.filter(pk=user.pk).update(username=username)
        user.username = username
    user.set_password(mdp)
    user.is_active = True
    user.mot_de_passe_provisoire = mdp
    user.mdp_modifie_par_utilisateur = False
    user.identifiants_maj_le = timezone.now()
    user.save()
    return mdp


def creer_ou_rattacher_compte(noms, prenoms, email, role, profils_occupes=()):
    """Crée un compte, ou rattache un compte existant de même e-mail s'il n'appartient à personne.

    Renvoie (user, erreur).
    """
    from users.models import CustomUser
    email = (email or "").strip().lower()
    existant = CustomUser.objects.filter(email__iexact=email).first() if email else None
    if existant:
        if hasattr(existant, "etudiant_profile") or hasattr(existant, "formateur_profile") or existant.pk in profils_occupes:
            return None, "Un autre compte utilise déjà cet e-mail."
        existant.role = role
        return existant, None
    user = CustomUser(noms=noms, prenoms=prenoms or "", email=email, username=nouvel_identifiant(noms, prenoms), role=role)
    return user, None


def appliquer_requete(request, user, creer=None):
    """Traite GET / POST (réinitialiser) / PATCH (activer) pour une vue d'identifiants.

    `creer` : fonction sans argument qui crée le compte quand il n'existe pas (POST), renvoie (user, erreur).
    Renvoie (statut_http, données).
    """
    if not est_admin(request.user):
        return 403, {"detail": "Accès réservé à l'administration."}
    if request.method == "GET":
        return 200, None
    if request.method == "PATCH":
        if not user:
            return 400, {"detail": "Pas encore de compte."}
        if "compte_actif" in request.data:
            user.is_active = str(request.data.get("compte_actif")).lower() in ("1", "true", "yes")
            user.save(update_fields=["is_active"])
        return 200, None
    # POST : réinitialisation (ou création)
    mdp = (request.data.get("mot_de_passe") or "").strip()
    if mdp and len(mdp) < 8:
        return 400, {"mot_de_passe": ["8 caractères minimum."]}
    regen = str(request.data.get("nouvel_identifiant", "")).lower() in ("1", "true", "yes")
    if not user:
        if not creer:
            return 400, {"detail": "Pas de compte."}
        user, err = creer()
        if err:
            return 400, {"detail": err}
        regen = False
    reinitialiser(user, mdp or None, regen)
    return 200, user

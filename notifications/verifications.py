"""Rappels périodiques (échéances en retard, séances à valider).

Lancés par la commande `python manage.py notifications_quotidiennes` (à planifier, ex. cron
chaque matin) et, à défaut, automatiquement au plus toutes les 6 heures quand un responsable
consulte ses notifications.
"""
import datetime as dt
import logging

from django.core.cache import cache
from django.utils import timezone

from .services import notifier
from .signals import montant

logger = logging.getLogger(__name__)


def verifier_echeances_en_retard(jour=None):
    from academique.models import AnneeAcademique
    from etudiants.models import Inscription
    from paiements.schedule_resolver import compute_student_retard

    jour = jour or timezone.localdate()
    annee = AnneeAcademique.objects.filter(est_active=True).first()
    if not annee:
        return 0
    nb, total, noms = 0, 0, []
    vus = set()
    for ins in Inscription.objects.filter(classe__annee_academique=annee).select_related("etudiant", "classe"):
        if ins.etudiant_id in vus:
            continue
        vus.add(ins.etudiant_id)
        r = compute_student_retard(ins.etudiant, ins.classe, jour)
        if r.get("is_overdue"):
            nb += 1
            total += float(r.get("overdue_amount") or 0)
            if len(noms) < 3:
                noms.append(ins.etudiant.nom)
    if nb:
        autres = f" et {nb - len(noms)} autre(s)" if nb > len(noms) else ""
        notifier(
            ["finance"], "echeances_retard",
            f"{nb} étudiant(s) en retard de paiement",
            f"Total en retard : {montant(total)} — {', '.join(noms)}{autres}",
            lien="/finances/scolarite", niveau="alerte", cle=f"retards-{jour.isoformat()}", inclure_auteur=True,
        )
    return nb


def verifier_seances_a_valider(jour=None):
    from academique.models import AnneeAcademique
    from emploidutemps.models import EmploiDuTemps, SeanceRealisee, periode_q
    from emploidutemps.seances import lister_seances, maintenant

    jour = jour or timezone.localdate()
    annee = AnneeAcademique.objects.filter(est_active=True).first()
    debut, fin = jour - dt.timedelta(days=14), jour
    qs = EmploiDuTemps.objects.filter(periode_q(debut, fin))
    srs = SeanceRealisee.objects.all()
    if annee:
        qs = qs.filter(classe__annee_academique=annee)
        srs = srs.filter(classe__annee_academique=annee)
    res = lister_seances(qs, srs, debut, fin, annee, maintenant(), "a_valider")
    nb = res["resume"]["a_valider"]
    if nb:
        heures = res["resume"]["minutes_a_valider"] / 60
        notifier(
            ["pedagogie"], "seances_a_valider",
            f"{nb} séance(s) à valider",
            f"Séances des 15 derniers jours en attente de validation ({heures:.0f} h) : les heures des formateurs ne sont pas comptées.",
            lien="/schedule/validation", niveau="alerte", cle=f"seances-{jour.isoformat()}", inclure_auteur=True,
        )
    return nb


def executer(force=False):
    """Exécute les rappels (au plus une fois toutes les 6 heures sauf `force`)."""
    if not force and not cache.add("notifications-verifications", True, 6 * 3600):
        return None
    resultats = {}
    from .signals_portail import verifier_echeances_etudiants

    for nom, f in (
        ("retards", verifier_echeances_en_retard),
        ("seances", verifier_seances_a_valider),
        ("echeances_etudiants", verifier_echeances_etudiants),
    ):
        try:
            resultats[nom] = f()
        except Exception:  # noqa: BLE001
            logger.exception("Vérification %s impossible", nom)
            resultats[nom] = None
    return resultats

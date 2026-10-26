"""Événements notifiés aux responsables (Finances, Étudiants, Pédagogie)."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import notifier

logger = logging.getLogger(__name__)


def montant(v):
    try:
        return f"{float(v):,.0f}".replace(",", " ") + " FCFA"
    except (TypeError, ValueError):
        return f"{v} FCFA"


def sans_echec(fonction):
    """Une notification ne doit jamais faire échouer l'enregistrement d'origine."""
    def wrapper(*args, **kwargs):
        try:
            fonction(*args, **kwargs)
        except Exception:  # noqa: BLE001
            logger.exception("Notification non envoyée (%s)", fonction.__name__)
    return wrapper


# ---------------------------------------------------------------- Finances
@receiver(post_save, sender="academique.PreInscription")
@sans_echec
def preinscription_recue(sender, instance, created, **kwargs):
    if not created:
        return
    filiere = getattr(instance.filiere_souhaitee, "nom", "") if instance.filiere_souhaitee_id else ""
    notifier(
        ["finance", "etudiants"], "preinscription",
        f"Nouvelle préinscription : {instance.nom_candidat} {instance.prenom_candidat}",
        f"{filiere or 'Filière non précisée'} · {instance.telephone or instance.email}",
        lien="/finances/preinscriptions",
    )


@receiver(post_save, sender="paiements.Paiement")
@sans_echec
def paiement_enregistre(sender, instance, created, **kwargs):
    if not created or not instance.etudiant_id:
        return
    type_ = "inscription" if instance.paiement_type == "INSCRIPTION" else "formation"
    reste = f" · reste {montant(instance.solde_restant)}" if instance.solde_restant is not None else ""
    notifier(
        ["finance"], "paiement_recu",
        f"Paiement reçu : {montant(instance.montant_paye)}",
        f"{instance.etudiant.nom} — frais de {type_}{reste}",
        lien="/finances/scolarite", niveau="succes",
    )


@receiver(post_save, sender="depenses.Depense")
@sans_echec
def depense_a_valider(sender, instance, created, **kwargs):
    if created and str(instance.statut).lower().startswith("en attente"):
        notifier(["finance"], "depense_a_valider", f"Dépense à valider : {montant(instance.montant)}", instance.libelle, lien="/finances", niveau="alerte")


@receiver(post_save, sender="revenus.Revenu")
@sans_echec
def revenu_a_valider(sender, instance, created, **kwargs):
    if created and str(instance.statut).lower().startswith("en attente"):
        notifier(["finance"], "revenu_a_valider", f"Revenu à valider : {montant(instance.montant)}", instance.libelle, lien="/finances", niveau="alerte")


# ---------------------------------------------------------------- Étudiants / Pédagogie
SEUILS_ABSENCES = (3, 5, 10)


@receiver(post_save, sender="assiduite.AssiduiteRecord")
@sans_echec
def absence_enregistree(sender, instance, created, **kwargs):
    if not created:
        return
    etu = instance.etudiant
    quand = instance.date.strftime("%d-%m-%Y")
    horaire = ""
    if instance.heure_debut and instance.heure_fin:
        def h(t):
            return f"{t.hour}H{t.minute:02d}" if t.minute else f"{t.hour}H"
        horaire = f" ({h(instance.heure_debut)} - {h(instance.heure_fin)})"
    if instance.type == "ABSENCE":
        titre = f"Absence : {etu.nom}"
    else:
        titre = f"Retard de {instance.minutes_retard or '?'} min : {etu.nom}"
    notifier(["etudiants", "pedagogie"], f"assiduite_{instance.type.lower()}", titre,
             f"{instance.module.nom}{horaire} le {quand}", lien="/attendance")

    if instance.type == "ABSENCE":
        from assiduite.models import AssiduiteRecord
        nb = AssiduiteRecord.objects.filter(etudiant=etu, type="ABSENCE", justifie=False).count()
        if nb in SEUILS_ABSENCES:
            notifier(
                ["etudiants", "pedagogie"], "seuil_absences",
                f"{etu.nom} cumule {nb} absences non justifiées",
                "Seuil d'alerte atteint : pensez à contacter l'étudiant ou son parent.",
                lien="/attendance", niveau="urgent" if nb >= 5 else "alerte",
                cle=f"seuil-abs-{etu.pk}-{nb}", inclure_auteur=True,
            )

"""Alimentation automatique de la trésorerie par la scolarité, la paie et les anciens modules."""
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _sans_echec(f):
    def wrapper(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except Exception:  # noqa: BLE001 — la trésorerie ne doit jamais bloquer l'enregistrement d'origine
            logger.exception("Synchronisation trésorerie impossible (%s)", f.__name__)
    return wrapper


@receiver(post_save, sender="paiements.Paiement")
@_sans_echec
def paiement_enregistre(sender, instance, **kwargs):
    from .services import synchroniser_paiement
    synchroniser_paiement(instance)


@receiver(post_delete, sender="paiements.Paiement")
@_sans_echec
def paiement_supprime(sender, instance, **kwargs):
    from .services import annuler_source
    annuler_source("paiement", instance.pk, "Paiement de scolarité supprimé")


@receiver(post_save, sender="depenses.Depense")
@_sans_echec
def ancienne_depense(sender, instance, **kwargs):
    from .services import synchroniser_ancienne_depense
    synchroniser_ancienne_depense(instance)


@receiver(post_delete, sender="depenses.Depense")
@_sans_echec
def ancienne_depense_supprimee(sender, instance, **kwargs):
    from .services import annuler_source
    annuler_source("depense", instance.pk, "Dépense supprimée")


@receiver(post_save, sender="revenus.Revenu")
@_sans_echec
def ancien_revenu(sender, instance, **kwargs):
    from .services import synchroniser_ancien_revenu
    synchroniser_ancien_revenu(instance)


@receiver(post_delete, sender="revenus.Revenu")
@_sans_echec
def ancien_revenu_supprime(sender, instance, **kwargs):
    from .services import annuler_source
    annuler_source("revenu", instance.pk, "Recette supprimée")

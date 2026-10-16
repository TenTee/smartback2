"""Calcul centralisé des frais dus par un étudiant.

Toutes les vues qui affichent un montant dû (scolarité, tableau de bord financier,
portail étudiant, situation, échéanciers, solde d'un paiement) passent par ici, afin
que les frais personnalisés d'un étudiant (`FraisEtudiant`) soient pris en compte partout.
"""
from decimal import Decimal

from django.db.models import Q, Sum

ZERO = Decimal("0")


def frais_classe(classe):
    """Frais d'inscription et de formation définis pour la classe."""
    from .models import Frais

    if not classe:
        return {"inscription": ZERO, "formation": ZERO}
    qs = Frais.objects.filter(classe=classe)
    ins = qs.filter(libelle__icontains="inscription").aggregate(t=Sum("montant"))["t"] or ZERO
    form = qs.exclude(libelle__icontains="inscription").aggregate(t=Sum("montant"))["t"] or ZERO
    return {"inscription": Decimal(ins), "formation": Decimal(form)}


def personnalisation(etudiant, classe):
    from .models import FraisEtudiant

    if not etudiant or not classe:
        return None
    return FraisEtudiant.objects.filter(etudiant=etudiant, classe=classe).first()


def frais_etudiant(etudiant, classe):
    """Frais réellement dus par l'étudiant pour cette classe (personnalisés sinon ceux de la classe)."""
    base = frais_classe(classe)
    perso = personnalisation(etudiant, classe)
    ins = perso.frais_inscription if perso and perso.frais_inscription is not None else base["inscription"]
    form = perso.frais_formation if perso and perso.frais_formation is not None else base["formation"]
    return {
        "inscription": Decimal(ins),
        "formation": Decimal(form),
        "total": Decimal(ins) + Decimal(form),
        "classe_inscription": base["inscription"],
        "classe_formation": base["formation"],
        "personnalise_inscription": bool(perso and perso.frais_inscription is not None),
        "personnalise_formation": bool(perso and perso.frais_formation is not None),
        "personnalise": bool(perso and (perso.frais_inscription is not None or perso.frais_formation is not None)),
        "motif": perso.motif if perso else "",
        "modifie_le": perso.updated_at if perso else None,
    }


def inscription_de_l_annee(etudiant, year_id=None):
    """Inscription de l'étudiant pour l'année (ou la plus récente)."""
    qs = etudiant.inscriptions.select_related("classe", "classe__annee_academique")
    if year_id:
        return qs.filter(Q(annee_academique_ref_id=year_id) | Q(classe__annee_academique_id=year_id)).order_by("-date_inscription", "-id").first()
    return qs.order_by("-date_inscription", "-id").first()


def montant_du_par_type(etudiant, classe, paiement_type):
    f = frais_etudiant(etudiant, classe)
    return f["inscription"] if paiement_type == "INSCRIPTION" else f["formation"]

"""Règles de gestion de la trésorerie."""
import datetime as dt
import logging
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import CategorieFinance, ClotureCaisse, CompteTresorerie, Operation

logger = logging.getLogger(__name__)

PREFIXES = {Operation.RECETTE: "REC", Operation.DEPENSE: "DEP", Operation.VIREMENT: "VIR", Operation.REPORT: "REP"}

# Catégories par défaut (codes utilisés par les opérations automatiques)
CATEGORIES_DEFAUT = [
    # code, libellé, sens, compte OHADA, système
    ("SCO-INS", "Frais d'inscription", "recette", "7061", True),
    ("SCO-FOR", "Frais de formation (scolarité)", "recette", "7062", True),
    ("REC-EXA", "Frais d'examen et de dossier", "recette", "7063", False),
    ("REC-SUB", "Subventions et dons", "recette", "71", False),
    ("REC-LOC", "Locations d'infrastructures", "recette", "7083", False),
    ("REC-VEN", "Ventes de produits et services", "recette", "701", False),
    ("REC-AUT", "Autres produits", "recette", "758", True),
    ("SAL", "Salaires et rémunérations", "depense", "661", True),
    ("CHS", "Charges sociales (CNPS…)", "depense", "664", False),
    ("VAC", "Vacations des formateurs", "depense", "6324", False),
    ("LOY", "Loyers et charges locatives", "depense", "622", False),
    ("EAU", "Eau, électricité, énergie", "depense", "605", False),
    ("FOU", "Fournitures de bureau et consommables", "depense", "604", False),
    ("PED", "Matériel et supports pédagogiques", "depense", "6047", False),
    ("ENT", "Entretien, réparations et nettoyage", "depense", "624", False),
    ("TEL", "Téléphone, internet, logiciels", "depense", "628", False),
    ("TRA", "Transports et déplacements", "depense", "618", False),
    ("COM", "Communication et publicité", "depense", "627", False),
    ("HON", "Honoraires et prestations", "depense", "632", False),
    ("ACT", "Activités extrascolaires et événements", "depense", "638", False),
    ("BAN", "Frais bancaires et mobile money", "depense", "631", False),
    ("IMP", "Impôts et taxes", "depense", "64", False),
    ("INV", "Investissements (équipements, mobilier)", "depense", "24", False),
    ("DEP-AUT", "Autres charges", "depense", "658", True),
]
COMPTES_DEFAUT = [
    ("Caisse principale", CompteTresorerie.CAISSE),
    ("Banque principale", CompteTresorerie.BANQUE),
    ("Mobile Money", CompteTresorerie.MOBILE),
]
# Anciens moyens de paiement (scolarité) → mode de trésorerie
MODES_PAIEMENT = {
    "cash": "especes", "especes": "especes", "mobile_money": "mobile_money", "orange_money": "mobile_money",
    "virement": "virement", "cheque": "cheque", "carte": "carte",
}


class OperationVerrouillee(Exception):
    pass


def initialiser():
    """Crée les comptes et catégories par défaut s'ils n'existent pas (idempotent)."""
    for i, (code, libelle, sens, cpt, systeme) in enumerate(CATEGORIES_DEFAUT):
        CategorieFinance.objects.get_or_create(code=code, defaults={
            "libelle": libelle, "sens": sens, "compte_comptable": cpt, "systeme": systeme, "ordre": i,
        })
    if not CompteTresorerie.objects.exists():
        for i, (nom, type_) in enumerate(COMPTES_DEFAUT):
            CompteTresorerie.objects.create(nom=nom, type=type_, ordre=i)


def categorie(code):
    c = CategorieFinance.objects.filter(code=code).first()
    if c is None:
        initialiser()
        c = CategorieFinance.objects.filter(code=code).first()
    return c


def compte_par_defaut(mode):
    """Compte utilisé pour un encaissement automatique selon le mode de paiement."""
    initialiser()
    voulu = {"especes": CompteTresorerie.CAISSE, "mobile_money": CompteTresorerie.MOBILE}.get(mode, CompteTresorerie.BANQUE)
    qs = CompteTresorerie.objects.filter(actif=True)
    return qs.filter(type=voulu).first() or qs.filter(type=CompteTresorerie.CAISSE).first() or qs.first()


def numeroter(type_, date):
    prefixe = f"{PREFIXES[type_]}-{date.year}-"
    dernier = Operation.objects.filter(numero__startswith=prefixe).aggregate(m=Max("numero"))["m"]
    n = int(dernier.rsplit("-", 1)[1]) + 1 if dernier else 1
    return f"{prefixe}{n:06d}"


def annee_pour(date=None):
    """Année académique d'une opération : l'année choisie dans l'application, sinon celle qui contient la date,
    sinon l'année active."""
    from academique.middleware import get_current_academic_year_id
    from academique.models import AnneeAcademique
    aid = get_current_academic_year_id()
    if aid and AnneeAcademique.objects.filter(pk=aid).exists():
        return aid
    return annee_par_date(date)


def annee_par_date(date=None):
    from academique.models import AnneeAcademique
    date = date or date_du_jour()
    a = (AnneeAcademique.objects.filter(date_debut__lte=date, date_fin__gte=date).first()
         or AnneeAcademique.objects.filter(est_active=True).first())
    return a.id if a else None


def creer_operation(**champs):
    """Crée une opération numérotée (réessaie si deux numéros sont pris en même temps).
    Toute opération appartient à une année académique."""
    if champs.get("annee_academique") is None:
        champs.pop("annee_academique", None)
    if not champs.get("annee_academique") and not champs.get("annee_academique_id"):
        champs["annee_academique_id"] = annee_par_date(champs.get("date"))
    for _ in range(6):
        try:
            with transaction.atomic():
                return Operation.objects.create(numero=numeroter(champs["type"], champs["date"]), **champs)
        except IntegrityError as e:
            if "numero" not in str(e) and "unique_operation_source" not in str(e) and "UNIQUE" not in str(e).upper():
                raise
            if champs.get("source_type") and Operation.objects.filter(source_type=champs["source_type"], source_id=champs.get("source_id")).exists():
                return Operation.objects.get(source_type=champs["source_type"], source_id=champs.get("source_id"))
    raise IntegrityError("Numérotation de l'opération impossible.")


def derniere_cloture(compte_id):
    return ClotureCaisse.objects.filter(compte_id=compte_id).order_by("-date").values_list("date", flat=True).first()


def verifier_verrou(date, *comptes):
    """Interdit de saisir / modifier une opération sur une période déjà clôturée."""
    for c in comptes:
        if not c:
            continue
        cid = c.pk if hasattr(c, "pk") else c
        d = derniere_cloture(cid)
        if d and date and date <= d:
            nom = c.nom if hasattr(c, "nom") else CompteTresorerie.objects.filter(pk=cid).values_list("nom", flat=True).first()
            raise OperationVerrouillee(f"La caisse « {nom} » est clôturée jusqu'au {d:%d/%m/%Y} : choisissez une date postérieure.")


def date_du_jour():
    return timezone.localdate()


# ---------------------------------------------------------------------------
# Synchronisation des autres modules (scolarité, paie, anciennes recettes / dépenses)
# ---------------------------------------------------------------------------
def synchroniser_paiement(paiement, compte=None):
    """Paiement de scolarité → recette validée (créée ou mise à jour)."""
    mode = MODES_PAIEMENT.get(paiement.moyen_paiement or "cash", "especes")
    cat = categorie("SCO-INS" if paiement.paiement_type == "INSCRIPTION" else "SCO-FOR")
    date = timezone.localtime(paiement.date_paiement).date() if paiement.date_paiement else date_du_jour()
    etu = paiement.etudiant
    libelle = f"{'Inscription' if paiement.paiement_type == 'INSCRIPTION' else 'Scolarité'} — {getattr(etu, 'nom', '')}".strip(" —")
    op = Operation.objects.filter(source_type="paiement", source_id=paiement.pk).first()
    compte = compte or getattr(paiement, "compte_tresorerie", None) or (op.compte if op else None) or compte_par_defaut(mode)
    valeurs = {
        "montant": paiement.montant_paye, "categorie": cat, "mode": mode, "compte": compte, "libelle": libelle[:255],
        "tiers": getattr(etu, "nom", "")[:200], "etudiant": etu, "annee_academique_id": paiement.annee_academique_id,
    }
    if op:
        for k, v in valeurs.items():
            if k == "annee_academique_id" and not v:
                continue
            setattr(op, k, v)
        op.save()
        return op
    return creer_operation(type=Operation.RECETTE, date=date, statut=Operation.VALIDEE, source="scolarite",
                           source_type="paiement", source_id=paiement.pk, valide_le=timezone.now(), **valeurs)


def annuler_source(source_type, source_id, motif):
    Operation.objects.filter(source_type=source_type, source_id=source_id).exclude(statut=Operation.ANNULEE).update(
        statut=Operation.ANNULEE, motif_rejet=motif[:255])


CATEGORIES_ANCIENNES_DEPENSES = {"Materiel": "PED", "Entretien": "ENT", "Logistique": "TRA", "Activites": "ACT", "Autres": "DEP-AUT"}
CATEGORIES_ANCIENNES_RECETTES = {"Inscription": "SCO-INS", "Examen": "REC-EXA", "Subvention": "REC-SUB", "Activite": "REC-AUT",
                                 "Location": "REC-LOC", "Vente": "REC-VEN", "Autres": "REC-AUT"}


def synchroniser_ancienne_depense(dep):
    """Dépense de l'ancien module (créée notamment par la paie) → dépense de trésorerie."""
    est_salaire = str(dep.libelle or "").lower().startswith("salaire")
    code = "SAL" if est_salaire else CATEGORIES_ANCIENNES_DEPENSES.get(dep.categorie, "DEP-AUT")
    statut = dep.statut or ""
    if statut.lower().startswith("valid"):
        st = Operation.VALIDEE
    elif statut.lower().startswith("rejet"):
        st = Operation.REJETEE
    else:
        st = Operation.EN_ATTENTE
    tiers = ""
    try:
        tiers = getattr(dep.responsable, "nom", "") or ""
    except Exception:  # noqa: BLE001
        tiers = ""
    op = Operation.objects.filter(source_type="depense", source_id=dep.pk).first()
    valeurs = {"montant": dep.montant, "categorie": categorie(code), "libelle": str(dep.libelle)[:255], "tiers": tiers[:200], "statut": st}
    if op:
        for k, v in valeurs.items():
            setattr(op, k, v)
        if st == Operation.VALIDEE and not op.compte_id:
            op.compte = compte_par_defaut("especes")
        op.save()
        return op
    return creer_operation(type=Operation.DEPENSE, date=dep.date_depense or date_du_jour(),
                           compte=compte_par_defaut("especes") if st == Operation.VALIDEE else None,
                           source="paie" if est_salaire else "ancien", source_type="depense", source_id=dep.pk,
                           mode="especes", **valeurs)


def synchroniser_ancien_revenu(rev):
    """Revenu de l'ancien module → recette de trésorerie « à valider ».

    Un revenu déclaré n'est pas forcément de l'argent en caisse (doublon d'un paiement de scolarité,
    montant attendu…) : il n'entre dans les soldes qu'après validation dans « Recettes & dépenses ».
    """
    rejete = (rev.statut or "").lower().startswith("rejet")
    op = Operation.objects.filter(source_type="revenu", source_id=rev.pk).first()
    valeurs = {"categorie": categorie(CATEGORIES_ANCIENNES_RECETTES.get(rev.categorie, "REC-AUT")),
               "libelle": str(rev.libelle)[:255], "tiers": str(rev.responsable or "")[:200]}
    if op:
        if op.statut in (Operation.EN_ATTENTE, Operation.APPROUVEE):
            valeurs["montant"] = rev.montant
            if rejete:
                valeurs.update(statut=Operation.REJETEE, motif_rejet="Revenu rejeté dans l'ancien module")
        elif op.statut == Operation.VALIDEE and rejete and not op.rapprochement_id:
            valeurs.update(statut=Operation.ANNULEE, motif_rejet="Revenu rejeté dans l'ancien module")
        for k, v in valeurs.items():
            setattr(op, k, v)
        op.save()
        return op
    notes = NOTE_DOUBLON if rev.categorie == "Inscription" else ""
    return creer_operation(type=Operation.RECETTE, date=rev.date_entree or date_du_jour(), compte=compte_par_defaut("especes"),
                           source="ancien", source_type="revenu", source_id=rev.pk, mode="especes", montant=rev.montant,
                           statut=Operation.REJETEE if rejete else Operation.EN_ATTENTE, notes=notes, **valeurs)


NOTE_DOUBLON = ("Revenu « Inscription » de l'ancien module : vérifiez qu'il ne fait pas doublon avec un paiement "
                "de scolarité (déjà compté en caisse) avant de le valider.")


# ---------------------------------------------------------------------------
# Indicateurs
# ---------------------------------------------------------------------------
def periode_annee(annee):
    if annee and annee.date_debut and annee.date_fin:
        return annee.date_debut, annee.date_fin
    today = date_du_jour()
    return dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)


def recouvrement(annee):
    """Scolarité de l'année : attendu, encaissé, reste, par classe."""
    from django.db.models import Sum

    from etudiants.models import Inscription
    from paiements.frais_etudiant import frais_etudiant
    from paiements.models import Paiement

    lignes = {}
    ins_qs = Inscription.objects.filter(classe__isnull=False).select_related("classe", "etudiant")
    if annee:
        ins_qs = ins_qs.filter(Q(annee_academique_ref=annee) | Q(classe__annee_academique=annee))
    payes = Paiement.objects.all()
    if annee:
        payes = payes.filter(annee_academique=annee)
    paye_par_etu = {r["etudiant_id"]: r["t"] for r in payes.values("etudiant_id").annotate(t=Sum("montant_paye"))}
    vus = set()
    for ins in ins_qs:
        if ins.etudiant_id in vus:
            continue
        vus.add(ins.etudiant_id)
        f = frais_etudiant(ins.etudiant, ins.classe)
        paye = Decimal(paye_par_etu.get(ins.etudiant_id) or 0)
        l = lignes.setdefault(ins.classe_id, {"classe_id": ins.classe_id, "classe": ins.classe.nom, "effectif": 0,
                                               "attendu": Decimal(0), "encaisse": Decimal(0), "soldes": 0})
        l["effectif"] += 1
        l["attendu"] += f["total"]
        l["encaisse"] += paye
        if paye >= f["total"] and f["total"] > 0:
            l["soldes"] += 1
    res = []
    for l in sorted(lignes.values(), key=lambda x: x["classe"]):
        reste = max(Decimal(0), l["attendu"] - l["encaisse"])
        res.append({**l, "attendu": float(l["attendu"]), "encaisse": float(l["encaisse"]), "reste": float(reste),
                    "taux": round(float(l["encaisse"]) * 100 / float(l["attendu"]), 1) if l["attendu"] else 0})
    return res

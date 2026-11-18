"""Tableau de bord de l'administration, adapté aux droits de l'utilisateur connecté.

GET /api/v2/tableau-de-bord/   (année : en-tête X-Academic-Year)

Chaque domaine (étudiants, pédagogie, finances, logistique, ressources humaines) n'est calculé
et renvoyé que si le rôle y a accès. « a_traiter » regroupe les points qui demandent une action.
"""
import datetime as dt
import logging

from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
CHAMPS = {
    "etudiants": "can_manage_etudiants",
    "pedagogie": "can_manage_pedagogie",
    "finance": "can_manage_finance",
    "logistique": "can_manage_logistique",
    "rh": "can_manage_rh",
}


def droits_de(user):
    from notifications.services import est_super_admin
    from users.models import Role
    from users.serializers import niveau_acces
    if est_super_admin(user):
        return {d: "ecriture" for d in CHAMPS}
    role = Role.objects.filter(code=user.role).first() if getattr(user, "role", None) else None
    return {d: niveau_acces(getattr(role, c, "none") if role else "none") for d, c in CHAMPS.items()}


def _annee(request):
    from academique.middleware import get_current_academic_year_id
    from academique.models import AnneeAcademique
    aid = get_current_academic_year_id()
    a = AnneeAcademique.objects.filter(pk=aid).first() if aid else None
    return a or AnneeAcademique.objects.filter(est_active=True).first()


def _sur(fonction, *args):
    """Une section en erreur n'empêche pas l'affichage des autres."""
    try:
        return fonction(*args)
    except Exception:  # noqa: BLE001
        logger.exception("Tableau de bord : section %s", fonction.__name__)
        return {"erreur": True}


def _mois(qs, champ):
    return [{"mois": (r["m"].date() if hasattr(r["m"], "date") else r["m"]).strftime("%Y-%m"), "nombre": r["n"]}
            for r in qs.annotate(m=TruncMonth(champ)).values("m").annotate(n=Count("id")).order_by("m") if r["m"]]


# ---------------------------------------------------------------------------
def section_etudiants(annee, today):
    from attestations.models import DemandeDocument
    from assiduite.models import AssiduiteRecord
    from etudiants.models import Inscription

    from .models import PreInscription
    from .sigles import sigle_classe

    ins = Inscription.objects.all()
    if annee:
        ins = ins.filter(Q(annee_academique_ref=annee) | Q(classe__annee_academique=annee))
    inscrits = ins.filter(statut="Inscrit")
    par_filiere = [
        {"filiere": r["classe__filiere__nom"] or "Sans classe", "nombre": r["n"]}
        for r in inscrits.values("classe__filiere__nom").annotate(n=Count("etudiant", distinct=True)).order_by("-n")[:8]
    ]
    dernieres = []
    for i in ins.select_related("etudiant", "classe__filiere", "classe__cycle", "classe__niveau").order_by("-date_inscription", "-id")[:6]:
        dernieres.append({"etudiant_id": i.etudiant_id, "nom": i.etudiant.nom, "matricule": i.etudiant.matricule,
                          "classe": sigle_classe(i.classe) if i.classe_id else "", "classe_nom": i.classe.nom if i.classe_id else "",
                          "date": i.date_inscription, "statut": i.statut})
    ass = AssiduiteRecord.objects.filter(date=today)
    return {
        "inscrits": inscrits.values("etudiant").distinct().count(),
        "pre_inscrits": ins.filter(statut="Pré-inscrit").values("etudiant").distinct().count(),
        "nouveaux_7j": ins.filter(date_inscription__gte=today - dt.timedelta(days=7)).count(),
        "preinscriptions_en_ligne": PreInscription.objects.filter(statut="EN_ATTENTE").count(),
        "demandes_documents": DemandeDocument.objects.filter(statut=DemandeDocument.EN_ATTENTE).count(),
        "documents_prets": DemandeDocument.objects.filter(statut=DemandeDocument.PRETE).count(),
        "absences_jour": ass.filter(type="ABSENCE").count(),
        "retards_jour": ass.filter(type="RETARD").count(),
        "par_filiere": par_filiere,
        "evolution": _mois(ins, "date_inscription")[-8:],
        "dernieres_inscriptions": dernieres,
    }


def section_pedagogie(annee, today):
    from emploidutemps.models import EmploiDuTemps, periode_q
    from formateurs.models import Formateur
    from modules.models import Module

    from .models import Classe
    from .sigles import sigle_classe

    classes = Classe.objects.filter(annee_academique=annee) if annee else Classe.objects.all()
    seances = (EmploiDuTemps.objects.filter(jour__iexact=JOURS[today.weekday()]).filter(periode_q(today, today))
               .select_related("module", "classe__filiere", "classe__cycle", "classe__niveau", "formateur", "salle")
               .order_by("heure_debut"))
    if annee:
        seances = seances.filter(Q(classe__annee_academique=annee) | Q(classe__isnull=True))
    maintenant = timezone.localtime().time()
    liste = [{
        "heure_debut": s.heure_debut.strftime("%H:%M"), "heure_fin": s.heure_fin.strftime("%H:%M"),
        "module": s.module.nom, "classe": sigle_classe(s.classe) if s.classe_id else "",
        "formateur": s.formateur.nom if s.formateur_id else "", "salle": s.salle.nom if s.salle_id else "",
        "en_cours": s.heure_debut <= maintenant <= s.heure_fin, "terminee": s.heure_fin < maintenant,
    } for s in seances[:40]]
    return {
        "classes": classes.count(),
        "formateurs": Formateur.objects.count(),
        "modules": Module.objects.count(),
        "seances_jour": len(liste),
        "seances": liste[:8],
    }


def section_finance(request):
    from tresorerie.views import TableauDeBordView
    d = TableauDeBordView().get(request).data
    a = d.get("a_faire", {})
    return {
        "tresorerie": d["tresorerie"]["total"],
        "scolarite": d["scolarite"] | {"classes": None},
        "mois": d["mois"],
        "periode_totaux": d["periode_totaux"],
        "evolution": d["evolution"][-6:],
        "depenses_a_approuver": a.get("a_approuver", {}).get("nombre", 0),
        "recettes_a_valider": a.get("recettes_a_valider", {}).get("nombre", 0),
        "a_payer_en_retard": a.get("en_retard", 0),
        "caisses_a_cloturer": a.get("caisses_a_cloturer", []),
    }


def section_logistique(request):
    from inventaires.views import InventaireStatsView
    d = InventaireStatsView().get(request).data
    return {k: d.get(k) for k in ("total_exemplaires", "en_utilisation", "en_panne", "en_maintenance", "pannes_ouvertes",
                                   "pannes_urgentes", "articles_stock_bas", "valeur_nette", "nb_emplacements")} | {
        "campagne_en_cours": (d.get("campagne_en_cours") or {}).get("reference"),
        "dernieres_pannes": [{"reference": p.get("reference"), "materiel": " ".join(x for x in (p.get("article_nom"), p.get("exemplaire_reference")) if x),
                              "lieu": p.get("emplacement_chemin") or "", "priorite_libelle": p.get("priorite_libelle"),
                              "priorite": p.get("priorite"), "statut": p.get("statut")} for p in (d.get("dernieres_pannes") or [])[:4]],
    }


def section_rh(today):
    from absences.models import DemandeAbsence
    from conges.models import Conge
    from personnels.models import Personnel
    return {
        "personnel": Personnel.objects.count(),
        "conges_en_attente": Conge.objects.filter(statut="en_attente").count(),
        "absences_en_attente": DemandeAbsence.objects.filter(statut="en_attente").count(),
        "en_conge_aujourdhui": Conge.objects.filter(statut="accepte", date_debut__lte=today, date_fin__gte=today).count(),
    }


# ---------------------------------------------------------------------------
def _a_traiter(s):
    items = []

    def ajouter(cle, libelle, nombre, lien, niveau="info"):
        if nombre:
            items.append({"cle": cle, "libelle": libelle, "nombre": nombre, "lien": lien, "niveau": niveau})

    e = s.get("etudiants") or {}
    ajouter("preinscriptions", "Pré-inscriptions en ligne à examiner", e.get("preinscriptions_en_ligne"), "/finances/preinscriptions", "alerte")
    ajouter("pre_inscrits", "Inscriptions à valider (pré-inscrits)", e.get("pre_inscrits"), "/students", "info")
    ajouter("documents", "Demandes de documents des étudiants", e.get("demandes_documents"), "/students/documents", "alerte")
    ajouter("documents_prets", "Documents prêts à remettre", e.get("documents_prets"), "/students/documents", "info")
    f = s.get("finance") or {}
    ajouter("depenses", "Dépenses à approuver", f.get("depenses_a_approuver"), "/finances/operations", "alerte")
    ajouter("recettes", "Recettes à valider", f.get("recettes_a_valider"), "/finances/operations", "info")
    ajouter("retard_paiement", "Paiements fournisseurs en retard", f.get("a_payer_en_retard"), "/finances/operations", "urgent")
    ajouter("caisses", "Caisses à clôturer", len(f.get("caisses_a_cloturer") or []), "/finances/tresorerie", "alerte")
    lo = s.get("logistique") or {}
    ajouter("pannes_urgentes", "Pannes urgentes", lo.get("pannes_urgentes"), "/inventory/maintenance", "urgent")
    ajouter("pannes", "Pannes ouvertes", (lo.get("pannes_ouvertes") or 0) - (lo.get("pannes_urgentes") or 0), "/inventory/maintenance", "alerte")
    ajouter("stock", "Articles en stock bas", lo.get("articles_stock_bas"), "/inventory/consommables", "info")
    r = s.get("rh") or {}
    ajouter("conges", "Demandes de congé à traiter", r.get("conges_en_attente"), "/leaves", "alerte")
    ajouter("absences_rh", "Absences du personnel à traiter", r.get("absences_en_attente"), "/absences", "info")
    ordre = {"urgent": 0, "alerte": 1, "info": 2}
    return sorted(items, key=lambda x: ordre[x["niveau"]])


class TableauDeBordAdminView(APIView):
    def get(self, request):
        from notifications.services import profil
        if profil(request.user) != "personnel":
            return Response({"detail": "Réservé au personnel."}, status=404)
        droits = droits_de(request.user)
        annee = _annee(request)
        today = timezone.localdate()
        a = lambda d: droits[d] != "none"  # noqa: E731
        sections = {}
        if a("etudiants"):
            sections["etudiants"] = _sur(section_etudiants, annee, today)
        if a("pedagogie"):
            sections["pedagogie"] = _sur(section_pedagogie, annee, today)
        if a("finance"):
            sections["finance"] = _sur(section_finance, request)
        if a("logistique"):
            sections["logistique"] = _sur(section_logistique, request)
        if a("rh"):
            sections["rh"] = _sur(section_rh, today)
        u = request.user
        return Response({
            "utilisateur": {"prenom": u.prenoms or u.username, "nom": f"{u.prenoms or ''} {u.noms or ''}".strip() or u.username},
            "annee": {"id": annee.id, "libelle": annee.libelle} if annee else None,
            "date": today,
            "droits": droits,
            "sections": sections,
            "a_traiter": _a_traiter(sections),
        })

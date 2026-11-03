"""Conditions de délivrance de l'attestation de réussite professionnelle.

Un étudiant peut la recevoir pour une année académique si :
  1. il est inscrit (inscription validée) pour l'année ;
  2. il a soldé toute sa scolarité de l'année (inscription + formation, frais personnalisés compris) ;
  3. il a toutes ses notes : pour chaque module de sa classe, la note de CC et la note de SN (ou de rattrapage) ;
  4. sa moyenne générale (notes finales pondérées par les coefficients) est au moins égale à 10/20.
"""
from decimal import Decimal

from django.db.models import Q, Sum

MOYENNE_REQUISE = 10.0


def _fcfa(v):
    return f"{Decimal(v or 0):,.0f}".replace(",", " ") + " FCFA"


def _mention(m):
    if m is None:
        return ""
    if m >= 16:
        return "Très Bien"
    if m >= 14:
        return "Bien"
    if m >= 12:
        return "Assez Bien"
    if m >= 10:
        return "Passable"
    return "Insuffisant"


def _modules_attendus(classe, ins, notes):
    """Modules du programme de la classe (sinon du niveau, sinon ceux qui ont des notes)."""
    mods = list(classe.modules.all()) if classe else []
    if not mods and ins and getattr(ins, "niveau_id", None) and hasattr(ins.niveau, "modules"):
        try:
            mods = list(ins.niveau.modules.all())
        except Exception:  # noqa: BLE001
            mods = []
    if not mods:
        vus = {}
        for n in notes:
            vus.setdefault(n.module_id, n.module)
        mods = list(vus.values())
    return sorted(mods, key=lambda m: (str(getattr(m, "semestre", "") or ""), m.nom))


def _meilleure_note(notes_module):
    """Plusieurs notes pour un module : on garde la plus complète."""
    def score(n):
        return (n.note_cc is not None) + (n.note_sn is not None or n.note_rattrapage is not None) + (n.note_finale is not None)
    return max(notes_module, key=score) if notes_module else None


def conditions_reussite(etudiant, annee):
    from notes.models import Note
    from paiements.frais_etudiant import frais_etudiant
    from paiements.models import Paiement

    from .services import inscription_de

    conditions = []
    ins = inscription_de(etudiant, annee)
    classe = ins.classe if ins else None
    libelle_annee = annee.libelle if annee else "l'année"

    # 1. Inscription
    inscrit = bool(ins and ins.statut == "Inscrit" and classe)
    conditions.append({
        "cle": "inscription", "libelle": "Inscription validée pour l'année", "ok": inscrit,
        "detail": (f"Inscrit(e) en {classe.nom} ({libelle_annee})" if inscrit else
                   (f"Inscription au statut « {ins.statut} »" if ins else f"Aucune inscription pour {libelle_annee}")),
    })

    # 2. Scolarité soldée
    du = paye = Decimal(0)
    if classe:
        du = Decimal(frais_etudiant(etudiant, classe)["total"])
        pq = Paiement.objects.filter(etudiant=etudiant)
        if annee:
            pq = pq.filter(annee_academique=annee)
        paye = Decimal(pq.aggregate(t=Sum("montant_paye"))["t"] or 0)
    reste = max(Decimal(0), du - paye)
    conditions.append({
        "cle": "scolarite", "libelle": "Scolarité entièrement soldée", "ok": bool(classe) and reste <= 0,
        "detail": (f"Payé {_fcfa(paye)} sur {_fcfa(du)}" if reste <= 0 else f"Reste à payer : {_fcfa(reste)} (payé {_fcfa(paye)} sur {_fcfa(du)})"),
        "reste": float(reste),
    })

    # 3. Toutes les notes (CC et SN/rattrapage)
    notes = list(Note.objects.filter(etudiant=etudiant).select_related("module").filter(
        Q(classe=classe) if classe else Q(annee_academique_ref=annee)
    )) if (classe or annee) else []
    par_module = {}
    for n in notes:
        par_module.setdefault(n.module_id, []).append(n)
    modules = _modules_attendus(classe, ins, notes)
    manquantes, points, coeffs, detail_notes = [], 0.0, 0, []
    for m in modules:
        n = _meilleure_note(par_module.get(m.id, []))
        manque = []
        if not n or n.note_cc is None:
            manque.append("CC")
        if not n or (n.note_sn is None and n.note_rattrapage is None):
            manque.append("SN")
        if manque:
            manquantes.append(f"{m.nom} ({' et '.join(manque)})")
        nf = float(n.note_finale) if n and n.note_finale is not None and not manque else None
        if nf is not None:
            c = getattr(m, "coefficient", 1) or 1
            points += nf * c
            coeffs += c
        detail_notes.append({"module": m.nom, "code": getattr(m, "code_ue", "") or "", "coefficient": getattr(m, "coefficient", 1) or 1,
                             "credits": getattr(m, "credits", 0) or 0, "note": nf, "semestre": getattr(m, "semestre", "") or ""})
    toutes = bool(modules) and not manquantes
    conditions.append({
        "cle": "notes", "libelle": "Toutes les notes saisies (CC et SN de chaque module)", "ok": toutes,
        "detail": (f"{len(modules)} module(s) complet(s)" if toutes else
                   ("Aucun module au programme de la classe" if not modules else
                    f"{len(manquantes)} module(s) incomplet(s) : " + ", ".join(manquantes[:12]) + (" …" if len(manquantes) > 12 else ""))),
        "manquantes": manquantes,
    })

    # 4. Moyenne générale ≥ 10
    moyenne = round(points / coeffs, 2) if coeffs else None
    conditions.append({
        "cle": "moyenne", "libelle": f"Moyenne générale d'au moins {MOYENNE_REQUISE:g}/20", "ok": toutes and moyenne is not None and moyenne >= MOYENNE_REQUISE,
        "detail": ("Moyenne non calculable : notes incomplètes" if not toutes else
                   f"Moyenne générale : {moyenne:.2f}/20".replace(".", ",")),
    })

    credits = sum(d["credits"] for d in detail_notes if d["note"] is not None and d["note"] >= 10)
    return {
        "eligible": all(c["ok"] for c in conditions),
        "conditions": conditions,
        "moyenne": moyenne,
        "mention": _mention(moyenne) if toutes else "",
        "credits_valides": credits,
        "total_credits": sum(d["credits"] for d in detail_notes),
        "notes": detail_notes,
        "classe": classe.nom if classe else None,
        "annee": libelle_annee,
        "etudiant": {"id": etudiant.id, "nom": etudiant.nom, "matricule": etudiant.matricule},
    }


def message_conditions(etudiant, resultat):
    manquantes = [c for c in resultat["conditions"] if not c["ok"]]
    lignes = "; ".join(f"{c['libelle']} — {c['detail']}" for c in manquantes)
    return f"{etudiant.nom} ne remplit pas les conditions de l'attestation de réussite : {lignes}."

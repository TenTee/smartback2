"""Séances (occurrences datées) des créneaux d'emploi du temps et leur validation."""
from datetime import timedelta

from django.utils import timezone

JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}


def maintenant(now=None):
    now = now or timezone.now()
    return timezone.localtime(now) if timezone.is_aware(now) else now


def annee_academique(annee_id=None):
    from academique.models import AnneeAcademique

    qs = AnneeAcademique.objects.all()
    if annee_id:
        a = qs.filter(pk=annee_id).first()
        if a:
            return a
    return qs.filter(est_active=True).first() or qs.order_by("-libelle").first()


def minutes(t):
    return t.hour * 60 + t.minute


def duree_prevue(entry):
    return max(0, minutes(entry.heure_fin) - minutes(entry.heure_debut))


def bornes(entry, annee):
    """Période effective d'un créneau : la sienne, sinon celle de l'année académique."""
    debut = entry.date_debut or (annee.date_debut if annee else None)
    fin = entry.date_fin or (annee.date_fin if annee else None)
    return debut, fin


def occurrences(entry, annee, start=None, end=None):
    """Dates des séances d'un créneau dans [start, end] (bornées par la période du créneau)."""
    wd = JOURS.get(str(entry.jour or "").strip().lower())
    if wd is None:
        return []
    debut, fin = bornes(entry, annee)
    if start:
        debut = max(debut, start) if debut else start
    if end:
        fin = min(fin, end) if fin else end
    if not debut or not fin or fin < debut:
        return []
    d = debut + timedelta(days=(wd - debut.weekday()) % 7)
    res = []
    while d <= fin:
        res.append(d)
        d += timedelta(days=7)
    return res


def est_passee(d, heure_fin, now):
    """La séance du jour `d` est terminée (heure de fin passée)."""
    return d < now.date() or (d == now.date() and heure_fin <= now.time())


def date_valide_pour(entry, d, annee):
    return d in occurrences(entry, annee, d, d)


JOURS_NOMS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _hm(t):
    return t.hour * 60 + t.minute


def lister_seances(creneaux, validations, debut, fin, annee, now, statut=None):
    """Séances datées entre `debut` et `fin` avec leur état de validation.

    creneaux     : queryset d'EmploiDuTemps (déjà filtré)
    validations  : queryset de SeanceRealisee (déjà filtré)
    """
    creneaux = creneaux.select_related("module", "classe", "formateur", "salle")
    srs = list(validations.select_related("module", "classe", "formateur", "valide_par").filter(date__gte=debut, date__lte=fin))
    records = {(r.emploi_id, r.date): r for r in srs if r.emploi_id}

    def depuis_validation(r):
        return {
            "valide_par": f"{r.valide_par.noms} {r.valide_par.prenoms}".strip() if r.valide_par else "",
            "valide_le": r.valide_le,
            "statut": r.statut,
            "duree_validee": r.duree_minutes,
            "commentaire": r.commentaire,
            "seance_id": r.id,
        }

    rows = []
    for e in creneaux:
        if not e.classe_id:
            continue
        for d in occurrences(e, annee, debut, fin):
            passee = est_passee(d, e.heure_fin, now)
            row = {
                "key": f"{e.id}_{d.isoformat()}",
                "emploi_id": e.id, "date": d, "jour": e.jour,
                "heure_debut": e.heure_debut, "heure_fin": e.heure_fin, "duree_prevue": duree_prevue(e),
                "classe_id": e.classe_id, "classe_nom": e.classe.nom if e.classe else "",
                "module_id": e.module_id, "module_nom": e.module.nom,
                "formateur_id": e.formateur_id, "formateur_nom": e.formateur.nom,
                "salle_nom": e.salle.nom if e.salle_id else "",
                "passee": passee, "permanent": not e.date_debut,
                "statut": "a_valider" if passee else "a_venir",
                "duree_validee": None, "commentaire": "", "valide_par": "", "valide_le": None, "seance_id": None,
            }
            r = records.pop((e.id, d), None)
            if r:
                row.update(depuis_validation(r))
            rows.append(row)
    # Validations dont le créneau a été supprimé ou modifié : conservées dans l'historique
    for r in [r for r in srs if not r.emploi_id] + list(records.values()):
        rows.append({
            "key": f"s{r.id}", "emploi_id": r.emploi_id, "date": r.date, "jour": JOURS_NOMS[r.date.weekday()],
            "heure_debut": r.heure_debut, "heure_fin": r.heure_fin,
            "duree_prevue": max(0, _hm(r.heure_fin) - _hm(r.heure_debut)),
            "classe_id": r.classe_id, "classe_nom": r.classe.nom if r.classe else "",
            "module_id": r.module_id, "module_nom": r.module.nom,
            "formateur_id": r.formateur_id, "formateur_nom": r.formateur.nom, "salle_nom": "",
            "passee": True, "permanent": False, "hors_programmation": True, **depuis_validation(r),
        })
    if statut:
        rows = [x for x in rows if x["statut"] == statut]
    rows.sort(key=lambda x: (x["date"], x["heure_debut"], x["classe_nom"]))
    resume = {k: sum(1 for x in rows if x["statut"] == k) for k in ("a_valider", "effectuee", "non_effectuee", "a_venir")}
    resume["minutes_validees"] = sum(x["duree_validee"] or 0 for x in rows if x["statut"] == "effectuee")
    resume["minutes_a_valider"] = sum(x["duree_prevue"] for x in rows if x["statut"] == "a_valider")
    return {"date_debut": debut, "date_fin": fin, "resume": resume, "seances": rows}

"""Fiche de suivi des heures d'un formateur, calculée à partir de la programmation
des emplois du temps (créneaux datés ou permanents) de l'année académique."""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}


def _annee(annee_id):
    from academique.models import AnneeAcademique

    qs = AnneeAcademique.objects.all()
    if annee_id:
        a = qs.filter(pk=annee_id).first()
        if a:
            return a
    return qs.filter(est_active=True).first() or qs.order_by("-libelle").first()


def _minutes(t):
    return t.hour * 60 + t.minute


def _occurrences(entry, annee, today, now_time):
    """Dates des séances d'un créneau : (passées, à venir) sur la période du créneau
    (ou, pour un créneau permanent, sur l'année académique)."""
    wd = JOURS.get(str(entry.jour or "").strip().lower())
    if wd is None:
        return [], []
    debut = entry.date_debut or (annee.date_debut if annee else None)
    fin = entry.date_fin or (annee.date_fin if annee else None)
    if not debut:
        # Créneau permanent sans dates d'année : on ne peut compter que la semaine en cours
        debut = today - timedelta(days=today.weekday())
    if not fin:
        fin = max(today, debut)
    first = debut + timedelta(days=(wd - debut.weekday()) % 7)
    passees, a_venir = [], []
    d = first
    while d <= fin:
        if d < today or (d == today and entry.heure_fin <= now_time):
            passees.append(d)
        else:
            a_venir.append(d)
        d += timedelta(days=7)
    return passees, a_venir


def _statut(volume, dispense_total, a_venir):
    if volume and dispense_total >= volume:
        return "Terminé"
    if dispense_total > 0:
        return "En cours"
    if a_venir > 0:
        return "Programmé"
    return "Non commencé"


def compute_suivi(formateur, annee_id=None, now=None):
    from academique.models import Classe
    from emploidutemps.models import EmploiDuTemps

    annee = _annee(annee_id)
    now = now or timezone.now()
    if timezone.is_aware(now):
        now = timezone.localtime(now)
    today, now_time = now.date(), now.time()

    classes_annee = Classe.objects.filter(annee_academique=annee) if annee else Classe.objects.none()
    edt_annee = EmploiDuTemps.objects.select_related("module", "classe")
    if annee:
        edt_annee = edt_annee.filter(classe__annee_academique=annee)

    mes_creneaux = list(edt_annee.filter(formateur=formateur))
    modules = {m.id: m for m in formateur.specialites.all()}
    for e in mes_creneaux:
        modules.setdefault(e.module_id, e.module)

    # Heures (en minutes) par (module, classe) : les miennes et toutes confondues
    def agg(entries):
        res = defaultdict(lambda: {"passe": 0, "avenir": 0, "seances": 0, "derniere": None, "prochaine": None})
        for e in entries:
            if not e.classe_id:
                continue
            duree = max(0, _minutes(e.heure_fin) - _minutes(e.heure_debut))
            passees, a_venir = _occurrences(e, annee, today, now_time)
            r = res[(e.module_id, e.classe_id)]
            r["passe"] += duree * len(passees)
            r["avenir"] += duree * len(a_venir)
            r["seances"] += len(passees)
            if passees and (r["derniere"] is None or passees[-1] > r["derniere"]):
                r["derniere"] = passees[-1]
            if a_venir and (r["prochaine"] is None or a_venir[0] < r["prochaine"]):
                r["prochaine"] = a_venir[0]
        return res

    mine = agg(mes_creneaux)
    tous = agg(edt_annee.filter(module_id__in=list(modules)))

    lignes = []
    tot = defaultdict(float)
    classes_vues, classes_commencees = set(), set()
    for mid, module in sorted(modules.items(), key=lambda kv: kv[1].nom.lower()):
        volume = float(module.duree or 0)
        rattachees = {c.id: c for c in classes_annee.filter(modules=module)}
        mes_classes_ids = {cid for (m, cid) in mine if m == mid}
        for cid in mes_classes_ids - set(rattachees):
            c = Classe.objects.filter(pk=cid).first()
            if c:
                rattachees[cid] = c
        classes = []
        for cid, c in sorted(rattachees.items(), key=lambda kv: kv[1].nom):
            m = mine.get((mid, cid), {"passe": 0, "avenir": 0, "seances": 0, "derniere": None, "prochaine": None})
            t = tous.get((mid, cid), {"passe": 0})
            mes_h = m["passe"] / 60
            total_h = t["passe"] / 60
            avenir_h = m["avenir"] / 60
            classes.append({
                "classe_id": cid,
                "classe_nom": c.nom,
                "assure_par_moi": cid in mes_classes_ids,
                "volume": volume,
                "heures_dispensees": round(mes_h, 2),
                "heures_dispensees_autres": round(max(0.0, total_h - mes_h), 2),
                "heures_restantes": round(max(0.0, volume - total_h), 2),
                "heures_programmees_a_venir": round(avenir_h, 2),
                "nb_seances": m["seances"],
                "derniere_seance": m["derniere"],
                "prochaine_seance": m["prochaine"],
                "taux": round(min(100.0, 100 * total_h / volume), 1) if volume else 0,
                "statut": _statut(volume, total_h, avenir_h),
            })
        miennes = [x for x in classes if x["assure_par_moi"]]
        ligne = {
            "module_id": mid,
            "module_nom": module.nom,
            "code_ue": getattr(module, "code_ue", ""),
            "semestre": getattr(module, "semestre", ""),
            "specialite": mid in {s.id for s in formateur.specialites.all()},
            "volume_par_classe": volume,
            "nb_classes_rattachees": len(classes),
            "nb_classes_assurees": len(miennes),
            "nb_classes_commencees": sum(1 for x in miennes if x["heures_dispensees"] > 0),
            "heures_prevues": volume * len(miennes),
            "heures_dispensees": round(sum(x["heures_dispensees"] for x in miennes), 2),
            "heures_restantes": round(sum(x["heures_restantes"] for x in miennes), 2),
            "heures_programmees_a_venir": round(sum(x["heures_programmees_a_venir"] for x in miennes), 2),
            "classes": classes,
        }
        ligne["taux"] = round(min(100.0, 100 * ligne["heures_dispensees"] / ligne["heures_prevues"]), 1) if ligne["heures_prevues"] else 0
        lignes.append(ligne)
        for k in ("heures_prevues", "heures_dispensees", "heures_restantes", "heures_programmees_a_venir"):
            tot[k] += ligne[k]
        for x in miennes:
            classes_vues.add(x["classe_id"])
            if x["heures_dispensees"] > 0:
                classes_commencees.add(x["classe_id"])

    totaux = {k: round(v, 2) for k, v in tot.items()}
    for k in ("heures_prevues", "heures_dispensees", "heures_restantes", "heures_programmees_a_venir"):
        totaux.setdefault(k, 0)
    totaux.update({
        "nb_modules": len(lignes),
        "nb_classes": len(classes_vues),
        "nb_classes_commencees": len(classes_commencees),
        "taux": round(min(100.0, 100 * totaux["heures_dispensees"] / totaux["heures_prevues"]), 1) if totaux["heures_prevues"] else 0,
    })
    try:
        montant = float(formateur.taux_horaire or 0) * totaux["heures_dispensees"]
    except (TypeError, ValueError):
        montant = 0
    return {
        "formateur": {
            "id": formateur.id, "nom": formateur.nom, "email": formateur.email, "contact": formateur.contact,
            "type_formateur": formateur.type_formateur, "taux_horaire": float(formateur.taux_horaire or 0),
            "specialites": [m.nom for m in formateur.specialites.all()],
        },
        "annee": {"id": annee.id, "libelle": annee.libelle, "date_debut": annee.date_debut, "date_fin": annee.date_fin} if annee else None,
        "date_calcul": now.isoformat(timespec="minutes"),
        "totaux": {**totaux, "montant_estime": round(montant, 2)},
        "modules": lignes,
    }

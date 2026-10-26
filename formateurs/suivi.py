"""Fiche de suivi des heures d'un formateur, calculée à partir de la programmation
des emplois du temps (créneaux datés ou permanents) de l'année académique."""
from collections import defaultdict
from datetime import timedelta

from emploidutemps.seances import annee_academique as _annee, est_passee, maintenant, minutes as _minutes, occurrences


def _statut(volume, dispense_total, a_venir, a_valider=0):
    if volume and dispense_total >= volume:
        return "Terminé"
    if dispense_total > 0:
        return "En cours"
    if a_valider > 0:
        return "À valider"
    if a_venir > 0:
        return "Programmé"
    return "Non commencé"


def compute_suivi(formateur, annee_id=None, now=None):
    from academique.models import Classe
    from emploidutemps.models import EmploiDuTemps, SeanceRealisee

    annee = _annee(annee_id)
    now = maintenant(now)

    classes_annee = Classe.objects.filter(annee_academique=annee) if annee else Classe.objects.none()
    edt_annee = EmploiDuTemps.objects.select_related("module", "classe")
    seances_annee = SeanceRealisee.objects.all()
    if annee:
        edt_annee = edt_annee.filter(classe__annee_academique=annee)
        seances_annee = seances_annee.filter(classe__annee_academique=annee)

    mes_creneaux = list(edt_annee.filter(formateur=formateur))
    modules = {m.id: m for m in formateur.specialites.all()}
    for e in mes_creneaux:
        modules.setdefault(e.module_id, e.module)
    for sr in seances_annee.filter(formateur=formateur).select_related("module"):
        modules.setdefault(sr.module_id, sr.module)

    vide = lambda: {"passe": 0, "avenir": 0, "attente": 0, "non_eff": 0, "seances": 0, "derniere": None, "prochaine": None}  # noqa: E731
    mine = defaultdict(vide)
    tous = defaultdict(vide)

    # Heures dispensées = séances VALIDÉES « effectuée » uniquement
    for sr in seances_annee.filter(module_id__in=list(modules)).exclude(classe__isnull=True):
        key = (sr.module_id, sr.classe_id)
        for target, ok in ((tous[key], True), (mine[key], sr.formateur_id == formateur.id)):
            if not ok:
                continue
            if sr.statut == SeanceRealisee.EFFECTUEE:
                target["passe"] += sr.duree_minutes
                target["seances"] += 1
                if target["derniere"] is None or sr.date > target["derniere"]:
                    target["derniere"] = sr.date
            else:
                target["non_eff"] += 1

    # Séances passées non encore validées / séances à venir (programmation)
    traitees = set(seances_annee.filter(formateur=formateur).exclude(emploi__isnull=True).values_list("emploi_id", "date"))
    for e in mes_creneaux:
        if not e.classe_id:
            continue
        duree = max(0, _minutes(e.heure_fin) - _minutes(e.heure_debut))
        r = mine[(e.module_id, e.classe_id)]
        debut_connu = e.date_debut or (annee.date_debut if annee else None)
        start = None if debut_connu else now.date() - timedelta(days=now.date().weekday())
        end = None if (e.date_fin or (annee and annee.date_fin)) else max(now.date(), start or now.date())
        for d in occurrences(e, annee, start, end):
            if est_passee(d, e.heure_fin, now):
                if (e.id, d) not in traitees:
                    r["attente"] += duree
            else:
                r["avenir"] += duree
                if r["prochaine"] is None or d < r["prochaine"]:
                    r["prochaine"] = d

    lignes = []
    tot = defaultdict(float)
    classes_vues, classes_commencees = set(), set()
    for mid, module in sorted(modules.items(), key=lambda kv: kv[1].nom.lower()):
        volume = float(module.duree or 0)
        rattachees = {c.id: c for c in classes_annee.filter(modules=module)}
        mes_classes_ids = {cid for (m, cid), v in mine.items() if m == mid and (v["passe"] or v["avenir"] or v["attente"] or v["seances"] or v["non_eff"])}
        for cid in mes_classes_ids - set(rattachees):
            c = Classe.objects.filter(pk=cid).first()
            if c:
                rattachees[cid] = c
        classes = []
        for cid, c in sorted(rattachees.items(), key=lambda kv: kv[1].nom):
            m = mine.get((mid, cid)) or vide()
            t = tous.get((mid, cid)) or vide()
            mes_h = m["passe"] / 60
            total_h = t["passe"] / 60
            avenir_h = m["avenir"] / 60
            classes.append({
                "classe_id": cid,
                "classe_nom": c.nom,
                "assure_par_moi": cid in mes_classes_ids or m["seances"] > 0,
                "volume": volume,
                "heures_dispensees": round(mes_h, 2),
                "heures_dispensees_autres": round(max(0.0, total_h - mes_h), 2),
                "heures_restantes": round(max(0.0, volume - total_h), 2),
                "heures_programmees_a_venir": round(avenir_h, 2),
                "heures_a_valider": round(m["attente"] / 60, 2),
                "nb_seances_non_effectuees": m["non_eff"],
                "nb_seances": m["seances"],
                "derniere_seance": m["derniere"],
                "prochaine_seance": m["prochaine"],
                "taux": round(min(100.0, 100 * total_h / volume), 1) if volume else 0,
                "statut": _statut(volume, total_h, avenir_h, m["attente"]),
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
            "heures_a_valider": round(sum(x["heures_a_valider"] for x in miennes), 2),
            "classes": classes,
        }
        ligne["taux"] = round(min(100.0, 100 * ligne["heures_dispensees"] / ligne["heures_prevues"]), 1) if ligne["heures_prevues"] else 0
        lignes.append(ligne)
        for k in ("heures_prevues", "heures_dispensees", "heures_restantes", "heures_programmees_a_venir", "heures_a_valider"):
            tot[k] += ligne[k]
        for x in miennes:
            classes_vues.add(x["classe_id"])
            if x["heures_dispensees"] > 0:
                classes_commencees.add(x["classe_id"])

    totaux = {k: round(v, 2) for k, v in tot.items()}
    for k in ("heures_prevues", "heures_dispensees", "heures_restantes", "heures_programmees_a_venir", "heures_a_valider"):
        totaux.setdefault(k, 0)
    totaux.update({
        "nb_modules": len(lignes),
        "nb_classes": len(classes_vues),
        "nb_classes_commencees": len(classes_commencees),
        "taux": round(min(100.0, 100 * totaux["heures_dispensees"] / totaux["heures_prevues"]), 1) if totaux["heures_prevues"] else 0,
    })
    # Heures réellement passées devant les étudiants : une séance en tronc commun (plusieurs classes
    # en même temps) n'est comptée qu'une fois pour le formateur.
    face = {}
    for sr in seances_annee.filter(formateur=formateur, statut=SeanceRealisee.EFFECTUEE).select_related("emploi"):
        groupe = sr.emploi.tronc_commun if sr.emploi_id and sr.emploi is not None else None
        cle = ("tc", str(groupe), sr.date) if groupe else ("s", sr.id)
        face[cle] = max(face.get(cle, 0), sr.duree_minutes)
    totaux["heures_face_a_face"] = round(sum(face.values()) / 60, 2)
    totaux["heures_tronc_commun"] = round(max(0.0, totaux["heures_dispensees"] - totaux["heures_face_a_face"]), 2)
    try:
        montant = float(formateur.taux_horaire or 0) * totaux["heures_face_a_face"]
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

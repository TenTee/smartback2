"""Activités hors cours : contrôles de conflits, occurrences, libellés, notifications."""
import datetime as dt

from django.db.models import Q

from .models import ActiviteClasse, EmploiDuTemps, periode_q

JOURS_NOMS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
JOUR_INDEX = {j.lower(): i for i, j in enumerate(JOURS_NOMS)}
JOURNEE = (dt.time(0, 0), dt.time(23, 59))


def _h(t):
    return f"{t.hour}H{t.minute:02d}" if t.minute else f"{t.hour}H"


def _d(d):
    return d.strftime("%d/%m/%Y")


def chevauchement_heures(hd, hf):
    """Activités occupant au moins une partie de [hd, hf]."""
    return Q(journee_entiere=True) | Q(heure_debut__lt=hf, heure_fin__gt=hd)


def activites_en_conflit(jour, hd, hf, date_debut, date_fin, classes_ids=(), salle_id=None, formateur_id=None, exclure_id=None):
    """Activités sur le même jour de semaine, aux périodes et heures qui se chevauchent, partageant
    une classe, la salle ou le formateur."""
    qs = ActiviteClasse.objects.filter(jour__iexact=jour).filter(chevauchement_heures(hd, hf))
    if date_fin:
        qs = qs.filter(date_debut__lte=date_fin)
    if date_debut:
        qs = qs.filter(date_fin__gte=date_debut)
    qui = Q(pk__in=[])
    if classes_ids:
        qui |= Q(classes__in=list(classes_ids))
    if salle_id:
        qui |= Q(salle_id=salle_id)
    if formateur_id:
        qui |= Q(formateur_id=formateur_id)
    qs = qs.filter(qui).distinct()
    if exclure_id:
        qs = qs.exclude(pk=exclure_id)
    return qs


def message_conflit_cours(classe_id, jour, hd, hf, date_debut, date_fin, salle_id=None, formateur_id=None):
    """Pour un cours : message si une activité occupe la classe, la salle ou le formateur, sinon None."""
    act = activites_en_conflit(jour, hd, hf, date_debut, date_fin, [classe_id] if classe_id else [], salle_id, formateur_id).first()
    if not act:
        return None
    return f"📌 Conflit avec l'activité « {act.titre} » ({decrire_quand(act)})."


def conflits_activite(act_data, classes_ids, exclure_id=None):
    """Messages de conflit pour une activité (cours et autres activités des classes, de la salle, du formateur)."""
    jour, dd, df = act_data["jour"], act_data["date_debut"], act_data["date_fin"]
    if act_data.get("journee_entiere"):
        hd, hf = JOURNEE
    else:
        hd, hf = act_data["heure_debut"], act_data["heure_fin"]
    salle_id = getattr(act_data.get("salle"), "pk", None)
    formateur_id = getattr(act_data.get("formateur"), "pk", None)
    messages = []

    qui = Q(classe_id__in=list(classes_ids))
    if salle_id:
        qui |= Q(salle_id=salle_id)
    if formateur_id:
        qui |= Q(formateur_id=formateur_id)
    cours = (EmploiDuTemps.objects.filter(periode_q(dd, df)).filter(jour__iexact=jour, heure_debut__lt=hf, heure_fin__gt=hd)
             .filter(qui).select_related("module", "classe", "formateur", "salle").order_by("date_debut", "heure_debut"))
    for c in cours[:8]:
        if c.classe_id in classes_ids:
            raison = f"la classe {c.classe.nom} a cours"
        elif salle_id and c.salle_id == salle_id:
            raison = f"la salle {c.salle.nom} est occupée"
        else:
            raison = f"{c.formateur.nom} donne cours"
        periode = f"semaine du {_d(c.date_debut)}" if c.date_debut else "créneau permanent"
        messages.append(f"{raison} : {c.module.nom} {jour} {_h(c.heure_debut)}-{_h(c.heure_fin)} ({periode}).")
    for a in activites_en_conflit(jour, hd, hf, dd, df, classes_ids, salle_id, formateur_id, exclure_id)[:5]:
        messages.append(f"activité « {a.titre} » au même moment ({decrire_quand(a)}).")
    return messages


def decrire_quand(act):
    if act.recurrente:
        quand = f"chaque {act.jour.lower()} du {_d(act.date_debut)} au {_d(act.date_fin)}"
    else:
        quand = f"{act.jour.lower()} {_d(act.date_debut)}"
    if act.journee_entiere or not act.heure_debut:
        return f"{quand}, toute la journée"
    return f"{quand}, {_h(act.heure_debut)}-{_h(act.heure_fin)}"


def bornes_journee(classes):
    """Heures d'affichage d'une activité « journée entière » (journée la plus large des classes)."""
    debut, fin = None, None
    for c in classes:
        h = c.horaires()
        if h.get("debut_journee"):
            debut = min(debut, h["debut_journee"]) if debut else h["debut_journee"]
        if h.get("fin_journee"):
            fin = max(fin, h["fin_journee"]) if fin else h["fin_journee"]
    return debut or dt.time(8, 0), fin or dt.time(17, 0)


def occurrences(qs, debut, fin):
    """Occurrences datées des activités entre debut et fin (inclus)."""
    res = []
    for a in qs.prefetch_related("classes__cycle__type_cycle").select_related("salle", "formateur", "module"):
        classes = list(a.classes.all())
        wd = JOUR_INDEX.get(str(a.jour).strip().lower())
        if wd is None:
            continue
        d = max(a.date_debut, debut)
        d += dt.timedelta(days=(wd - d.weekday()) % 7)
        if a.journee_entiere or not a.heure_debut:
            hd, hf = bornes_journee(classes)
        else:
            hd, hf = a.heure_debut, a.heure_fin
        while d <= min(a.date_fin, fin):
            res.append({
                "key": f"act-{a.id}-{d.isoformat()}",
                "activite_id": a.id,
                "date": d.isoformat(),
                "jour": JOURS_NOMS[d.weekday()],
                "heure_debut": hd.strftime("%H:%M:%S"),
                "heure_fin": hf.strftime("%H:%M:%S"),
                "journee_entiere": a.journee_entiere,
                "titre": a.titre,
                "type": a.type,
                "type_libelle": a.get_type_display(),
                "couleur": a.couleur,
                "description": a.description,
                "recurrente": a.recurrente,
                "obligatoire": a.obligatoire,
                "lieu": a.salle.nom if a.salle_id else a.lieu,
                "salle_nom": a.salle.nom if a.salle_id else "",
                "responsable": a.formateur.nom if a.formateur_id else a.responsable,
                "module_nom": a.module.nom if a.module_id else "",
                "classes": [{"id": c.id, "nom": c.nom} for c in classes],
            })
            if not a.recurrente:
                break
            d += dt.timedelta(days=7)
    res.sort(key=lambda o: (o["date"], o["heure_debut"]))
    return res


def notifier_activite(act, action="ajout"):
    """Prévient les étudiants des classes et le formateur responsable."""
    try:
        from notifications.services import notifier_utilisateurs
        from users.models import CustomUser
    except Exception:  # noqa: BLE001
        return
    ids = list(act.classes.values_list("id", flat=True))
    etudiants = list(CustomUser.objects.filter(is_active=True, etudiant_profile__inscriptions__classe_id__in=ids).distinct())
    libelle = {"ajout": "Nouvelle activité", "modification": "Activité modifiée", "suppression": "Activité annulée"}[action]
    lieu = act.salle.nom if act.salle_id else act.lieu
    message = f"{act.get_type_display()} · {decrire_quand(act)}" + (f" · {lieu}" if lieu else "")
    from django.utils import timezone
    cle = f"activite-{act.pk}-{action}-{timezone.now():%Y%m%d%H%M}"
    niveau = "alerte" if action == "suppression" or act.type in ("evaluation", "devoir") else "info"
    notifier_utilisateurs(etudiants, "etudiant", f"activite_{action}", f"{libelle} : {act.titre}", message,
                          lien="/portal/schedule", niveau=niveau, cle=cle)
    if act.formateur_id and act.formateur.user_id:
        notifier_utilisateurs([act.formateur.user], "enseignement", f"activite_{action}", f"{libelle} : {act.titre}",
                              message, lien="/trainer/schedule", niveau=niveau, cle=cle)

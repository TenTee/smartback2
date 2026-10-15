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

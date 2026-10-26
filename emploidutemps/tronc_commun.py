"""Tronc commun : un même cours programmé au même moment pour plusieurs classes.

Les créneaux du groupe partagent `EmploiDuTemps.tronc_commun` (UUID) et les mêmes cours, formateur,
salle, jour, horaires et période. Modifier l'un modifie les autres ; les conflits de salle et de
formateur entre classes d'un même groupe sont ignorés (c'est le même cours).
"""
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q

from .models import EmploiDuTemps, periode_q

CHAMPS_PARTAGES = ("module_id", "formateur_id", "jour", "heure_debut", "heure_fin", "salle_id", "date_debut", "date_fin")


def nouvel_identifiant():
    return uuid.uuid4()


def adoptables(module_id, classes_ids, jour, heure_debut, heure_fin, date_debut, date_fin, sauf_pk=None):
    """Créneaux déjà saisis séparément pour ces classes, sur le même cours et le même créneau :
    ils seront rattachés au tronc commun au lieu d'être en conflit."""
    if not classes_ids:
        return EmploiDuTemps.objects.none()
    qs = EmploiDuTemps.objects.filter(
        classe_id__in=list(classes_ids), module_id=module_id, jour=jour,
        heure_debut=heure_debut, heure_fin=heure_fin, date_debut=date_debut, date_fin=date_fin,
    )
    return qs.exclude(pk=sauf_pk) if sauf_pk else qs


def _copier(source, cible):
    for champ in CHAMPS_PARTAGES:
        setattr(cible, champ, getattr(source, champ))
    cible.tronc_commun = source.tronc_commun


def synchroniser(principal, classes_ids=None):
    """Aligne le groupe sur le créneau `principal` (déjà enregistré).

    classes_ids : None → propage seulement les modifications aux classes déjà dans le groupe ;
                  liste → classes voulues (avec ou sans celle du principal) : ajoute / retire des classes.
    Lève DjangoValidationError (messages par classe) en cas de conflit : à appeler dans une transaction.
    """
    groupe = principal.tronc_commun
    existants = list(EmploiDuTemps.objects.filter(tronc_commun=groupe).exclude(pk=principal.pk).select_related("classe")) if groupe else []
    if classes_ids is None:
        voulues = {e.classe_id for e in existants}
    else:
        voulues = {int(c) for c in classes_ids if c} - {principal.classe_id}

    if not voulues:
        for e in existants:
            e.delete()
        if principal.tronc_commun:
            EmploiDuTemps.objects.filter(pk=principal.pk).update(tronc_commun=None)
            principal.tronc_commun = None
        return {"classes": 0, "ajoutees": 0, "retirees": len(existants)}

    if not groupe:
        groupe = nouvel_identifiant()
        principal.tronc_commun = groupe
        EmploiDuTemps.objects.filter(pk=principal.pk).update(tronc_commun=groupe)

    erreurs, retirees, ajoutees = [], 0, 0
    deja = {}
    for e in existants:
        if e.classe_id in voulues:
            deja[e.classe_id] = e
        else:
            e.delete()
            retirees += 1

    # Créneaux saisis séparément pour les nouvelles classes : on les rattache
    nouvelles = voulues - set(deja)
    a_rattacher = {}
    if nouvelles:
        anciens = adoptables(principal.module_id, nouvelles, principal.jour, principal.heure_debut, principal.heure_fin,
                             principal.date_debut, principal.date_fin, sauf_pk=principal.pk)
        for e in anciens.select_related("classe"):
            a_rattacher.setdefault(e.classe_id, e)
        if a_rattacher:
            EmploiDuTemps.objects.filter(pk__in=[e.pk for e in a_rattacher.values()]).update(tronc_commun=groupe)

    from academique.models import Classe
    classes = {c.id: c for c in Classe.objects.filter(pk__in=voulues)}
    for cid in sorted(voulues):
        classe = classes.get(cid)
        if classe is None:
            erreurs.append(f"Classe {cid} introuvable.")
            continue
        e = deja.get(cid) or a_rattacher.get(cid)
        if e is None:
            e = EmploiDuTemps(classe=classe)
            ajoutees += 1
        _copier(principal, e)
        try:
            e.save()
        except DjangoValidationError as exc:
            erreurs.append(f"{classe.nom} : {' '.join(exc.messages)}")
    if erreurs:
        raise DjangoValidationError(erreurs)
    return {"classes": len(voulues) + 1, "ajoutees": ajoutees, "retirees": retirees}


def classes_candidates(module_id, classe, jour=None, heure_debut=None, heure_fin=None, date_debut=None, date_fin=None, emploi=None):
    """Classes de la même année ayant ce cours, avec leur disponibilité sur le créneau."""
    from academique.models import Affectation, Classe

    groupe = emploi.tronc_commun if emploi else None
    membres = {}
    if groupe:
        membres = {e.classe_id: e for e in EmploiDuTemps.objects.filter(tronc_commun=groupe).exclude(pk=emploi.pk)}

    qs = Classe.objects.all()
    if classe is not None and classe.annee_academique_id:
        qs = qs.filter(annee_academique_id=classe.annee_academique_id)
    ids = set(qs.filter(modules__id=module_id).values_list("id", flat=True))
    ids |= set(Affectation.objects.filter(module_id=module_id, classe__in=qs).values_list("classe_id", flat=True))
    ids |= set(EmploiDuTemps.objects.filter(module_id=module_id, classe__in=qs).values_list("classe_id", flat=True))
    ids |= set(membres)
    if classe is not None:
        ids.discard(classe.id)

    resultat = []
    for c in Classe.objects.filter(pk__in=ids).select_related("filiere", "niveau").order_by("nom"):
        info = {
            "id": c.id, "nom": c.nom, "filiere_nom": getattr(c.filiere, "nom", ""),
            "dans_le_groupe": c.id in membres, "disponible": True, "raison": "", "rattachement": False,
        }
        if jour and heure_debut and heure_fin:
            occupe = EmploiDuTemps.objects.filter(periode_q(date_debut, date_fin)).filter(
                classe=c, jour=jour, heure_debut__lt=heure_fin, heure_fin__gt=heure_debut,
            ).select_related("module")
            if groupe:
                occupe = occupe.exclude(tronc_commun=groupe)
            if emploi:
                occupe = occupe.exclude(pk=emploi.pk)
            occupe = list(occupe)
            if occupe:
                memes = [o for o in occupe if o.module_id == int(module_id) and str(o.heure_debut)[:5] == str(heure_debut)[:5]
                         and str(o.heure_fin)[:5] == str(heure_fin)[:5] and o.date_debut == date_debut and o.date_fin == date_fin]
                if len(memes) == len(occupe):
                    info.update(rattachement=True, raison="Ce cours y est déjà programmé à ce créneau : il sera rattaché au tronc commun.")
                else:
                    o = next(x for x in occupe if x not in memes)
                    info.update(disponible=False, raison=f"Occupée : {o.module.nom} ({o.heure_debut:%H:%M}-{o.heure_fin:%H:%M})")
        resultat.append(info)
    return resultat

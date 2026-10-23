"""Séances de l'emploi du temps d'un étudiant pour une date donnée (pour l'assiduité)."""
from django.db.models import Q


def classe_pour_date(etudiant, jour, year_id=None):
    """Classe de l'étudiant à cette date : celle dont l'année académique couvre la date,
    sinon celle de l'année sélectionnée, sinon la plus récente."""
    inscriptions = list(
        etudiant.inscriptions.filter(classe__isnull=False)
        .select_related("classe", "classe__annee_academique")
        .order_by("-date_inscription", "-id")
    )
    for ins in inscriptions:
        a = ins.classe.annee_academique
        if a and a.date_debut and a.date_fin and a.date_debut <= jour <= a.date_fin:
            return ins.classe
    if year_id:
        for ins in inscriptions:
            if str(ins.annee_academique_ref_id) == str(year_id) or str(ins.classe.annee_academique_id) == str(year_id):
                return ins.classe
    return inscriptions[0].classe if inscriptions else None


def seances_du_jour(etudiant, jour, year_id=None):
    """(classe, [créneaux EmploiDuTemps ayant une séance ce jour-là, triés par heure])."""
    from emploidutemps.models import EmploiDuTemps, periode_q
    from emploidutemps.seances import occurrences

    classe = classe_pour_date(etudiant, jour, year_id)
    if not classe:
        return None, []
    annee = classe.annee_academique
    creneaux = (
        EmploiDuTemps.objects.filter(classe=classe)
        .filter(periode_q(jour, jour))
        .select_related("module", "formateur", "salle")
        .order_by("heure_debut")
    )
    return classe, [e for e in creneaux if occurrences(e, annee, jour, jour)]

"""Supports de cours : à quelles classes un support est destiné, et quels supports un étudiant peut voir."""
from django.db.models import Q


def classes_du_formateur(formateur, module_id=None, annee_id=None):
    """Classes où le formateur enseigne (affectations + emploi du temps), éventuellement pour un module."""
    from academique.models import Affectation, Classe
    from emploidutemps.models import EmploiDuTemps

    aff = Affectation.objects.filter(enseignant=formateur)
    edt = EmploiDuTemps.objects.filter(formateur=formateur)
    if module_id:
        aff = aff.filter(module_id=module_id)
        edt = edt.filter(module_id=module_id)
    ids = set(aff.values_list("classe_id", flat=True)) | set(edt.values_list("classe_id", flat=True))
    if not ids:
        # Comme « Mes classes » : à défaut d'affectation, les classes dont le programme contient ses spécialités
        mods = formateur.specialites.all()
        if module_id:
            mods = mods.filter(id=module_id)
        ids = set(Classe.modules.through.objects.filter(module__in=mods).values_list("classe_id", flat=True))
    qs = Classe.objects.filter(id__in=[i for i in ids if i])
    if annee_id:
        qs = qs.filter(annee_academique_id=annee_id)
    return qs


def classes_de_l_etudiant(etudiant):
    """Classe(s) de l'étudiant pour l'année choisie (à défaut, sa dernière inscription)."""
    from academique.middleware import get_current_academic_year_id

    ins = etudiant.inscriptions.filter(classe__isnull=False)
    annee_id = get_current_academic_year_id()
    if annee_id:
        de_l_annee = ins.filter(Q(annee_academique_ref_id=annee_id) | Q(classe__annee_academique_id=annee_id))
        if de_l_annee.exists():
            return list(de_l_annee.values_list("classe_id", flat=True).distinct())
    der = ins.order_by("-date_inscription", "-id").first()
    return [der.classe_id] if der else []


def supports_visibles(user):
    """Supports qu'un utilisateur du portail étudiant peut voir et télécharger.

    Un étudiant ne voit que les supports publiés pour SA classe. Les anciens supports sans classe
    restent visibles s'ils portent sur un module de sa classe (programme ou emploi du temps).
    """
    from emploidutemps.models import EmploiDuTemps

    from .models import CoursDocument

    qs = CoursDocument.objects.filter(est_visible_etudiants=True).select_related("module").prefetch_related("classes")
    etudiant = getattr(user, "etudiant_profile", None)
    if etudiant is None:
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs
        return qs.none()
    classes = classes_de_l_etudiant(etudiant)
    if not classes:
        return qs.none()
    from academique.models import Classe
    modules_classe = set(Classe.modules.through.objects.filter(classe_id__in=classes).values_list("module_id", flat=True))
    modules_classe |= set(EmploiDuTemps.objects.filter(classe_id__in=classes).values_list("module_id", flat=True))
    return qs.filter(Q(classes__in=classes) | Q(classes__isnull=True, module_id__in=modules_classe)).distinct()

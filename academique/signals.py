from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from academique.models import Filiere, Cycle, Niveau, Classe, AnneeAcademique


def _get_target_annees():
    return AnneeAcademique.objects.all()


def _create_classes_for(filiere, cycle, niveau):
    années = _get_target_annees()
    created = []
    for an in années:
        exists = Classe.objects.filter(filiere=filiere, cycle=cycle, niveau=niveau, annee_academique=an).exists()
        if not exists:
            classe = Classe.objects.create(filiere=filiere, cycle=cycle, niveau=niveau, annee_academique=an)
            created.append(classe)
    return created


@receiver(post_save, sender=Cycle)
def on_cycle_created(sender, instance, created, **kwargs):
    if not created:
        return
    filiere = instance.filiere
    for niveau in instance.niveaux.all():
        _create_classes_for(filiere, instance, niveau)


@receiver(post_save, sender=Niveau)
def on_niveau_created(sender, instance, created, **kwargs):
    if not created:
        return
    cycle = instance.cycle
    filiere = cycle.filiere
    _create_classes_for(filiere, cycle, instance)


@receiver(post_save, sender=Filiere)
def on_filiere_created(sender, instance, created, **kwargs):
    if not created:
        return
    for cycle in instance.cycles.all():
        for niveau in cycle.niveaux.all():
            _create_classes_for(instance, cycle, niveau)


@receiver(post_save, sender=AnneeAcademique)
def on_annee_academique_created(sender, instance, created, **kwargs):
    if not created:
        return
    source_annee = (
        AnneeAcademique.objects.filter(est_active=True).exclude(pk=instance.pk).first()
        or AnneeAcademique.objects.exclude(pk=instance.pk).order_by('-libelle').first()
    )
    if not source_annee:
        return
    for classe in Classe.objects.filter(annee_academique=source_annee):
        Classe.objects.get_or_create(
            filiere=classe.filiere,
            cycle=classe.cycle,
            niveau=classe.niveau,
            annee_academique=instance,
            defaults={"nom": f"{classe.filiere.nom} {classe.cycle.nom} {classe.niveau.ordre} ({instance.libelle})"},
        )


# ---------------------------------------------------------------------------
# Cours d'une classe communs à toutes les années académiques
# ---------------------------------------------------------------------------
# Une classe existe une fois par année académique (même filière / cycle / niveau).
# Les cours rattachés sont propagés à toutes ces classes : rattacher ou retirer un
# cours sur une année le fait pour toutes les autres. La propagation passe par la
# table de liaison (bulk), elle ne redéclenche donc pas ce signal.
@receiver(m2m_changed, sender=Classe.modules.through)
def sync_modules_between_years(sender, instance, action, reverse, pk_set, **kwargs):
    Through = Classe.modules.through
    if reverse:
        # instance = Module, pk_set = ids de classes
        if action not in ("post_add", "post_remove") or not pk_set:
            return
        module_id = instance.pk
        for classe in Classe.objects.filter(pk__in=pk_set):
            sibling_ids = list(classe.siblings().values_list("id", flat=True))
            if action == "post_add":
                Through.objects.bulk_create(
                    [Through(classe_id=cid, module_id=module_id) for cid in sibling_ids], ignore_conflicts=True
                )
            else:
                Through.objects.filter(classe_id__in=sibling_ids, module_id=module_id).delete()
        return

    if action == "pre_clear":
        instance._modules_before_clear = list(instance.modules.values_list("id", flat=True))
        return
    if action == "post_clear":
        pk_set = set(getattr(instance, "_modules_before_clear", []))
        action = "post_remove"
    if action not in ("post_add", "post_remove") or not pk_set:
        return
    sibling_ids = list(instance.siblings().values_list("id", flat=True))
    if not sibling_ids:
        return
    if action == "post_add":
        Through.objects.bulk_create(
            [Through(classe_id=cid, module_id=mid) for cid in sibling_ids for mid in pk_set], ignore_conflicts=True
        )
    else:
        Through.objects.filter(classe_id__in=sibling_ids, module_id__in=pk_set).delete()

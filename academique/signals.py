from django.db.models.signals import post_save
from django.dispatch import receiver

from academique.models import Filiere, Cycle, Niveau, Classe, AnneeAcademique


def _get_target_annees():
    années = AnneeAcademique.objects.filter(est_active=True)
    if années.exists():
        return années
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

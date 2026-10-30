"""Rattache chaque opération sans année académique à l'année qui contient sa date.

Séparé de 0004 : PostgreSQL refuse de mélanger dans une même transaction la création d'un index
(nouveau champ annee_origine) et des mises à jour de données (« pending trigger events »).
"""
from django.db import migrations


def rattacher(apps, schema_editor):
    """Chaque opération sans année académique est rattachée à l'année qui contient sa date
    (à défaut, l'année active, puis la plus proche)."""
    Operation = apps.get_model("tresorerie", "Operation")
    Annee = apps.get_model("academique", "AnneeAcademique")
    annees = [a for a in Annee.objects.exclude(date_debut__isnull=True).exclude(date_fin__isnull=True).order_by("date_debut")]
    active = Annee.objects.filter(est_active=True).first() or (annees[-1] if annees else Annee.objects.first())
    if not active:
        return
    for op in Operation.objects.filter(annee_academique__isnull=True).only("id", "date"):
        a = next((x for x in annees if x.date_debut <= op.date <= x.date_fin), None)
        if a is None and annees:
            avant = [x for x in annees if x.date_fin < op.date]
            a = avant[-1] if avant else annees[0]
        Operation.objects.filter(pk=op.pk).update(annee_academique=a or active)


class Migration(migrations.Migration):
    dependencies = [
        ("tresorerie", "0004_annee_par_operation"),
    ]
    operations = [migrations.RunPython(rattacher, migrations.RunPython.noop)]

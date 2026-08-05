from django.db import migrations


def backfill_preinscription_annee(apps, schema_editor):
    AnneeAcademique = apps.get_model("academique", "AnneeAcademique")
    PreInscription = apps.get_model("academique", "PreInscription")

    # D'abord s'assurer qu'une seule année est active
    actives = AnneeAcademique.objects.filter(est_active=True)
    if actives.count() > 1:
        # Garder seulement la plus récente comme active
        latest = actives.order_by("-libelle").first()
        actives.exclude(pk=latest.pk).update(est_active=False)

    # Prendre l'année active, ou sinon la plus récente
    annee = AnneeAcademique.objects.filter(est_active=True).first()
    if not annee:
        annee = AnneeAcademique.objects.order_by("-libelle").first()

    if annee:
        PreInscription.objects.filter(annee_academique__isnull=True).update(
            annee_academique=annee
        )


class Migration(migrations.Migration):

    dependencies = [
        ("academique", "0012_preinscription_annee_academique"),
    ]

    operations = [
        migrations.RunPython(backfill_preinscription_annee, migrations.RunPython.noop),
    ]

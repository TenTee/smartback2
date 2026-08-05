from django.db import migrations


def backfill_annee_ref(apps, schema_editor):
    Note = apps.get_model("notes", "Note")
    AnneeAcademique = apps.get_model("academique", "AnneeAcademique")
    Classe = apps.get_model("academique", "Classe")

    # 1. Notes avec une classe liée à une année : hériter de la classe
    for classe in Classe.objects.filter(annee_academique__isnull=False).only("id", "annee_academique_id"):
        Note.objects.filter(
            classe_id=classe.id,
            annee_academique_ref__isnull=True,
        ).update(annee_academique_ref_id=classe.annee_academique_id)

    # 2. Notes sans classe : matcher par libelle
    for annee in AnneeAcademique.objects.all():
        Note.objects.filter(
            annee_academique_ref__isnull=True,
            classe__isnull=True,
            annee_academique=annee.libelle,
        ).update(annee_academique_ref=annee)

    # 3. Notes restantes (pas de classe, libelle ne match rien) : assigner l'année active ou la plus récente
    remaining = Note.objects.filter(annee_academique_ref__isnull=True).count()
    if remaining > 0:
        annee = AnneeAcademique.objects.filter(est_active=True).first()
        if not annee:
            annee = AnneeAcademique.objects.order_by("-libelle").first()
        if annee:
            Note.objects.filter(annee_academique_ref__isnull=True).update(
                annee_academique_ref=annee
            )


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0003_note_annee_academique_ref"),
        ("academique", "0011_filiere_responsable_nom"),
    ]

    operations = [
        migrations.RunPython(backfill_annee_ref, migrations.RunPython.noop),
    ]

"""Rattache chaque support existant aux classes où son formateur enseigne ce module (affectations,
emploi du temps). Séparé de 0005 pour PostgreSQL (pas de données et de schéma dans la même transaction)."""
from django.db import migrations


def rattacher(apps, schema_editor):
    CoursDocument = apps.get_model("formateurs", "CoursDocument")
    Affectation = apps.get_model("academique", "Affectation")
    EmploiDuTemps = apps.get_model("emploidutemps", "EmploiDuTemps")
    for doc in CoursDocument.objects.all():
        ids = set(Affectation.objects.filter(enseignant_id=doc.formateur_id, module_id=doc.module_id).values_list("classe_id", flat=True))
        ids |= set(EmploiDuTemps.objects.filter(formateur_id=doc.formateur_id, module_id=doc.module_id).values_list("classe_id", flat=True))
        ids.discard(None)
        if ids:
            doc.classes.set(ids)


class Migration(migrations.Migration):
    dependencies = [
        ("formateurs", "0005_coursdocument_classes"),
        ("emploidutemps", "0008_activite_toutes_classes"),
    ]
    operations = [migrations.RunPython(rattacher, migrations.RunPython.noop)]

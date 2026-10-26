import uuid
from collections import defaultdict

from django.db import migrations, models


def regrouper(apps, schema_editor):
    """Les créneaux identiques (même cours, formateur, salle, jour, horaires, période) de plusieurs
    classes, saisis auparavant comme « tronc commun », deviennent un groupe."""
    EmploiDuTemps = apps.get_model("emploidutemps", "EmploiDuTemps")
    groupes = defaultdict(list)
    for e in EmploiDuTemps.objects.exclude(classe__isnull=True).only(
        "id", "classe_id", "module_id", "formateur_id", "salle_id", "jour", "heure_debut", "heure_fin", "date_debut", "date_fin"
    ):
        cle = (e.module_id, e.formateur_id, e.salle_id, e.jour, e.heure_debut, e.heure_fin, e.date_debut, e.date_fin)
        groupes[cle].append(e)
    for membres in groupes.values():
        if len({m.classe_id for m in membres}) > 1:
            EmploiDuTemps.objects.filter(pk__in=[m.pk for m in membres]).update(tronc_commun=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [("emploidutemps", "0005_seancerealisee")]

    operations = [
        migrations.AddField(
            model_name="emploidutemps",
            name="tronc_commun",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(regrouper, migrations.RunPython.noop),
    ]

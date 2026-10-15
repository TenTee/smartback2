from django.db import migrations


def harmoniser(apps, schema_editor):
    """Rend les cours d'une classe identiques sur toutes les années académiques
    (union des cours déjà rattachés aux classes de même filière / cycle / niveau)."""
    Classe = apps.get_model("academique", "Classe")
    Through = Classe.modules.through
    groupes = {}
    for c in Classe.objects.all().values("id", "filiere_id", "cycle_id", "niveau_id"):
        groupes.setdefault((c["filiere_id"], c["cycle_id"], c["niveau_id"]), []).append(c["id"])
    for ids in groupes.values():
        if len(ids) < 2:
            continue
        modules = set(Through.objects.filter(classe_id__in=ids).values_list("module_id", flat=True))
        Through.objects.bulk_create(
            [Through(classe_id=cid, module_id=mid) for cid in ids for mid in modules], ignore_conflicts=True
        )


class Migration(migrations.Migration):
    dependencies = [("academique", "0017_configurationetablissement_releve_config_cachet")]
    operations = [migrations.RunPython(harmoniser, migrations.RunPython.noop)]

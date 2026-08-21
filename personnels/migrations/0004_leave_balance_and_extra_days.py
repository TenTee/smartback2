from django.db import migrations, models


def set_default_leave_balance(apps, schema_editor):
    Personnel = apps.get_model("personnels", "Personnel")
    Personnel.objects.filter(solde_conges_initial=0).update(solde_conges_initial=20)
    Personnel.objects.filter(solde_conges_restant=0).update(solde_conges_restant=20)


class Migration(migrations.Migration):
    dependencies = [
        ("personnels", "0003_remove_personnel_fonction_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="personnel",
            name="jours_conges_supplementaires",
            field=models.PositiveIntegerField(default=0, verbose_name="Jours de congés supplémentaires"),
        ),
        migrations.AddField(
            model_name="personnel",
            name="motif_conges_supplementaires",
            field=models.TextField(default="", verbose_name="Motif des congés supplémentaires"),
        ),
        migrations.AlterField(
            model_name="personnel",
            name="solde_conges_initial",
            field=models.PositiveIntegerField(default=20, verbose_name="Solde de congés annuel"),
        ),
        migrations.RunPython(set_default_leave_balance, migrations.RunPython.noop),
    ]
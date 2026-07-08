import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academique", "0011_filiere_responsable_nom"),
    ]

    operations = [
        migrations.AddField(
            model_name="preinscription",
            name="annee_academique",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pre_inscriptions",
                to="academique.anneeacademique",
            ),
        ),
    ]

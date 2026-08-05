import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academique", "0011_filiere_responsable_nom"),
        ("notes", "0002_remove_note_note_tp"),
    ]

    operations = [
        migrations.AddField(
            model_name="note",
            name="annee_academique_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notes",
                to="academique.anneeacademique",
            ),
        ),
    ]

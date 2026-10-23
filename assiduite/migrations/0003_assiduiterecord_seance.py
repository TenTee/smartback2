import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assiduite", "0002_alter_assiduiterecord_justificatif"),
        ("emploidutemps", "0005_seancerealisee"),
    ]

    operations = [
        migrations.AddField(
            model_name="assiduiterecord",
            name="emploi",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assiduite", to="emploidutemps.emploidutemps"),
        ),
        migrations.AddField(model_name="assiduiterecord", name="heure_debut", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="assiduiterecord", name="heure_fin", field=models.TimeField(blank=True, null=True)),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("assiduite", "0003_assiduiterecord_seance"),
    ]

    operations = [
        migrations.AddField(
            model_name="assiduiterecord",
            name="justificatif_texte",
            field=models.TextField(blank=True, default=""),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academique", "0020_classe_journee"),
    ]

    operations = [
        migrations.AddField(
            model_name="configurationetablissement",
            name="nom_court",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
    ]

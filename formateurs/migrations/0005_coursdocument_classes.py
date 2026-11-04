from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academique", "0020_classe_journee"),
        ("formateurs", "0004_formateur_identifiants"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursdocument",
            name="classes",
            field=models.ManyToManyField(blank=True, related_name="cours_documents", to="academique.classe"),
        ),
    ]

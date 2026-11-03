from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attestations", "0002_type_releve"),
    ]

    operations = [
        migrations.AlterField(
            model_name="documentdelivre",
            name="type",
            field=models.CharField(
                choices=[
                    ("certificat", "Certificat de scolarité"),
                    ("carte", "Carte d'étudiant"),
                    ("releve", "Relevé de notes"),
                    ("reussite", "Attestation de réussite professionnelle"),
                ],
                max_length=20,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("emploidutemps", "0003_salle_alter_emploidutemps_salle"),
    ]

    operations = [
        migrations.AddField(
            model_name="emploidutemps",
            name="date_debut",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emploidutemps",
            name="date_fin",
            field=models.DateField(blank=True, null=True),
        ),
    ]

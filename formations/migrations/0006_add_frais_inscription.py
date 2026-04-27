# Generated manually to add registration fee field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formations', '0005_niveau_cycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='formation',
            name='frais_inscription',
            field=models.DecimalField(
                default=0,
                help_text="Montant des frais d'inscription en FCFA",
                max_digits=10,
                decimal_places=2,
            ),
        ),
    ]

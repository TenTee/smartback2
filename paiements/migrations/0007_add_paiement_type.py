# Generated manually to add payment type field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('paiements', '0006_frais_paiement_frais_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='paiement',
            name='paiement_type',
            field=models.CharField(
                choices=[
                    ('FORMATION', "Frais de formation"),
                    ('INSCRIPTION', "Frais d'inscription"),
                ],
                default='FORMATION',
                help_text="Type de paiement pour distinguer frais de formation et frais d'inscription",
                max_length=20,
            ),
        ),
    ]

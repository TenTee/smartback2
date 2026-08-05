from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formateurs', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='formateur',
            name='type_formateur',
            field=models.CharField(
                choices=[('permanent', 'Permanent'), ('vacataire', 'Vacataire')],
                default='permanent',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='formateur',
            name='taux_horaire',
            field=models.DecimalField(decimal_places=2, default=0.00, max_digits=10),
        ),
    ]

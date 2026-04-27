# Generated manually to add semester to Module
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modules', '0003_module_coefficient_module_has_tp_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='semestre',
            field=models.CharField(
                choices=[('Semestre 1', 'Semestre 1'), ('Semestre 2', 'Semestre 2')],
                default='Semestre 1',
                help_text='Semestre auquel appartient le cours',
                max_length=20,
            ),
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academique', '0004_alter_classe_options_alter_cycle_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='preinscription',
            name='formation_souhaitee',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pre_inscriptions',
                to='formations.formation',
            ),
        ),
    ]

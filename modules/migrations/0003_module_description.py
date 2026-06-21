from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('modules', '0002_remove_module_has_tp_remove_module_pourcentage_cc_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='description',
            field=models.TextField(blank=True, default=''),
        ),
    ]

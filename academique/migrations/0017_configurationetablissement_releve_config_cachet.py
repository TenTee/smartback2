from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academique', '0016_preinscription_date_naissance_preinscriptiondocument'),
    ]

    operations = [
        migrations.AddField(
            model_name='configurationetablissement',
            name='cachet',
            field=models.ImageField(blank=True, help_text='Cachet / tampon officiel apposé sur les documents', null=True, upload_to='etablissement/cachets/'),
        ),
        migrations.AddField(
            model_name='configurationetablissement',
            name='releve_config',
            field=models.JSONField(blank=True, default=dict, help_text='Paramètres de mise en page du relevé de notes PDF'),
        ),
    ]

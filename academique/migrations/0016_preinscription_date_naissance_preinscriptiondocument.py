from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academique', '0015_add_logo_entete'),
    ]

    operations = [
        migrations.AddField(
            model_name='preinscription',
            name='date_naissance',
            field=models.DateField(blank=True, null=True, verbose_name='Date de naissance'),
        ),
        migrations.CreateModel(
            name='PreInscriptionDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fichier', models.FileField(upload_to='pre_inscriptions/documents/')),
                ('type_document', models.CharField(blank=True, max_length=50)),
                ('date_upload', models.DateTimeField(auto_now_add=True)),
                ('pre_inscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='academique.preinscription')),
            ],
        ),
    ]

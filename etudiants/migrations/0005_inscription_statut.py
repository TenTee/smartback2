from django.db import migrations, models


def copy_statut(apps, schema_editor):
    """Les inscriptions existantes reprennent le statut global de l'étudiant."""
    Inscription = apps.get_model('etudiants', 'Inscription')
    for ins in Inscription.objects.select_related('etudiant').all():
        statut = getattr(ins.etudiant, 'statut', None) or 'Inscrit'
        if ins.statut != statut:
            ins.statut = statut
            ins.save(update_fields=['statut'])


class Migration(migrations.Migration):

    dependencies = [
        ('etudiants', '0004_etudiant_nom_parent_etudiant_whatsapp_parent'),
    ]

    operations = [
        migrations.AddField(
            model_name='inscription',
            name='statut',
            field=models.CharField(choices=[('Pré-inscrit', 'Pré-inscrit'), ('Inscrit', 'Inscrit')], default='Inscrit', max_length=20),
        ),
        migrations.RunPython(copy_statut, migrations.RunPython.noop),
    ]

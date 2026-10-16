from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("formateurs", "0003_add_user_link_and_cours_documents")]

    operations = [
        migrations.AddField(model_name="formateur", name="mot_de_passe_initial", field=models.CharField(blank=True, max_length=128, null=True)),
        migrations.AddField(model_name="formateur", name="mdp_modifie_par_formateur", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="formateur", name="identifiants_maj_le", field=models.DateTimeField(blank=True, null=True)),
    ]

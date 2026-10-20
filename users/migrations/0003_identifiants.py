from django.db import migrations, models


def reprendre_mots_de_passe(apps, schema_editor):
    """Reprend les mots de passe initiaux déjà connus (étudiants, formateurs) sur le compte utilisateur."""
    Etudiant = apps.get_model("etudiants", "Etudiant")
    Formateur = apps.get_model("formateurs", "Formateur")
    CustomUser = apps.get_model("users", "CustomUser")
    for e in Etudiant.objects.exclude(user__isnull=True).exclude(initial_password__isnull=True).exclude(initial_password=""):
        CustomUser.objects.filter(pk=e.user_id, mot_de_passe_provisoire__isnull=True).update(mot_de_passe_provisoire=e.initial_password)
    for f in Formateur.objects.exclude(user__isnull=True):
        if f.mot_de_passe_initial:
            CustomUser.objects.filter(pk=f.user_id).update(mot_de_passe_provisoire=f.mot_de_passe_initial, identifiants_maj_le=f.identifiants_maj_le)
        elif f.mdp_modifie_par_formateur:
            CustomUser.objects.filter(pk=f.user_id).update(mdp_modifie_par_utilisateur=True)


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_change_permissions_to_access_levels"),
        ("etudiants", "0005_inscription_statut"),
        ("formateurs", "0004_formateur_identifiants"),
    ]

    operations = [
        migrations.AddField(model_name="customuser", name="mot_de_passe_provisoire", field=models.CharField(blank=True, max_length=128, null=True)),
        migrations.AddField(model_name="customuser", name="mdp_modifie_par_utilisateur", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="customuser", name="identifiants_maj_le", field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(reprendre_mots_de_passe, migrations.RunPython.noop),
    ]

"""Les anciens droits booléens (convertis en texte « true » / « false ») deviennent « ecriture » / « none »."""
from django.db import migrations

CHAMPS = ("can_manage_rh", "can_manage_pedagogie", "can_manage_logistique", "can_manage_finance", "can_manage_etudiants")


def normaliser(apps, schema_editor):
    Role = apps.get_model("users", "Role")
    for role in Role.objects.all():
        modifie = False
        for champ in CHAMPS:
            v = str(getattr(role, champ) or "").strip().lower()
            if v in ("none", "lecture", "ecriture"):
                continue
            setattr(role, champ, "ecriture" if v in ("true", "1", "t", "oui", "écriture") else "none")
            modifie = True
        if modifie:
            role.save(update_fields=list(CHAMPS))


class Migration(migrations.Migration):
    dependencies = [("users", "0003_identifiants")]

    operations = [migrations.RunPython(normaliser, migrations.RunPython.noop)]

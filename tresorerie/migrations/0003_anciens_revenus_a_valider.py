"""Les revenus repris de l'ancien module ne sont plus comptés d'office dans la caisse.

Ils passent « à valider » : le responsable financier confirme dans « Recettes & dépenses » ceux qui
correspondent à de l'argent réellement reçu (et rejette les doublons des paiements de scolarité).
Les recettes déjà pointées sur un relevé bancaire ne sont pas touchées.
"""
from django.db import migrations

NOTE = ("Revenu « Inscription » de l'ancien module : vérifiez qu'il ne fait pas doublon avec un paiement "
        "de scolarité (déjà compté en caisse) avant de le valider.")


def a_valider(apps, schema_editor):
    Operation = apps.get_model("tresorerie", "Operation")
    Revenu = apps.get_model("revenus", "Revenu")
    inscriptions = set(Revenu.objects.filter(categorie="Inscription").values_list("id", flat=True))
    for op in Operation.objects.filter(source_type="revenu", statut="validee", rapprochement__isnull=True):
        op.statut = "en_attente"
        op.valide_par = None
        op.valide_le = None
        if op.source_id in inscriptions and NOTE not in (op.notes or ""):
            op.notes = f"{op.notes}\n{NOTE}".strip()
        op.save(update_fields=["statut", "valide_par", "valide_le", "notes"])


class Migration(migrations.Migration):
    dependencies = [
        ("tresorerie", "0002_reprise_donnees"),
        ("revenus", "0001_initial"),
    ]
    operations = [migrations.RunPython(a_valider, migrations.RunPython.noop)]

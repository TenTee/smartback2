from django.db import migrations, models
import django.db.models.deletion


def backfill_annee(apps, schema_editor):
    """Rattache chaque paiement existant à une année académique :
    1. l'année de la classe des frais payés ;
    2. sinon l'inscription de l'étudiant dont l'année couvre la date du paiement ;
    3. sinon la dernière inscription faite avant le paiement ;
    4. sinon la première inscription de l'étudiant."""
    Paiement = apps.get_model("paiements", "Paiement")
    Inscription = apps.get_model("etudiants", "Inscription")

    for p in Paiement.objects.filter(annee_academique__isnull=True).select_related("frais__classe"):
        year_id = None
        if p.frais_id and p.frais and p.frais.classe_id:
            year_id = p.frais.classe.annee_academique_id
        if not year_id and p.etudiant_id:
            inscriptions = list(
                Inscription.objects.filter(etudiant_id=p.etudiant_id, annee_academique_ref__isnull=False)
                .select_related("annee_academique_ref")
                .order_by("date_inscription", "id")
            )
            day = p.date_paiement.date() if p.date_paiement else None
            if day:
                for ins in inscriptions:
                    y = ins.annee_academique_ref
                    if y.date_debut and y.date_fin and y.date_debut <= day <= y.date_fin:
                        year_id = y.id
                        break
                if not year_id:
                    before = [ins for ins in inscriptions if ins.date_inscription and ins.date_inscription <= day]
                    if before:
                        year_id = before[-1].annee_academique_ref_id
            if not year_id and inscriptions:
                year_id = inscriptions[0].annee_academique_ref_id
        if year_id:
            Paiement.objects.filter(pk=p.pk).update(annee_academique_id=year_id)


class Migration(migrations.Migration):

    dependencies = [
        ("paiements", "0002_add_classe_payment_schedule"),
        ("academique", "0017_configurationetablissement_releve_config_cachet"),
        ("etudiants", "0005_inscription_statut"),
    ]

    operations = [
        migrations.AddField(
            model_name="paiement",
            name="annee_academique",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="paiements", to="academique.anneeacademique"),
        ),
        migrations.RunPython(backfill_annee, migrations.RunPython.noop),
    ]

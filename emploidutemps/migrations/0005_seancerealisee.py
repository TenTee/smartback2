import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("emploidutemps", "0004_emploidutemps_periode"),
        ("academique", "0018_classe_modules_toutes_annees"),
        ("formateurs", "__first__"),
        ("modules", "__first__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SeanceRealisee",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("statut", models.CharField(choices=[("effectuee", "Effectuée"), ("non_effectuee", "Non effectuée")], max_length=20)),
                ("heure_debut", models.TimeField()),
                ("heure_fin", models.TimeField()),
                ("duree_minutes", models.PositiveIntegerField(default=0, help_text="Durée réellement effectuée (minutes)")),
                ("commentaire", models.TextField(blank=True, default="")),
                ("valide_le", models.DateTimeField(auto_now=True)),
                ("classe", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seances_realisees", to="academique.classe")),
                ("emploi", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seances", to="emploidutemps.emploidutemps")),
                ("formateur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seances_realisees", to="formateurs.formateur")),
                ("module", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seances_realisees", to="modules.module")),
                ("valide_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seances_validees", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "heure_debut"]},
        ),
        migrations.AddConstraint(
            model_name="seancerealisee",
            constraint=models.UniqueConstraint(fields=("emploi", "date"), name="unique_seance_par_creneau_et_date"),
        ),
    ]

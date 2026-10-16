import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("paiements", "0003_paiement_annee_academique"),
        ("academique", "0018_classe_modules_toutes_annees"),
        ("etudiants", "0005_inscription_statut"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FraisEtudiant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("frais_inscription", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("frais_formation", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("motif", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("classe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="frais_etudiants", to="academique.classe")),
                ("etudiant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="frais_personnalises", to="etudiants.etudiant")),
                ("modifie_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="fraisetudiant",
            constraint=models.UniqueConstraint(fields=("etudiant", "classe"), name="unique_frais_etudiant_classe"),
        ),
        # Un échéancier personnel par classe (et non plus par filière) : permet un échéancier
        # propre chaque année, même quand l'étudiant reste dans la même filière.
        migrations.RemoveConstraint(model_name="studentpaymentplan", name="unique_student_plan_per_filiere"),
        migrations.AddConstraint(
            model_name="studentpaymentplan",
            constraint=models.UniqueConstraint(fields=("etudiant", "classe"), name="unique_student_plan_per_classe"),
        ),
    ]

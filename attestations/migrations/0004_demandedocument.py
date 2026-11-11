import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attestations", "0003_type_reussite"),
        ("academique", "0021_configurationetablissement_nom_court"),
        ("etudiants", "0005_inscription_statut"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DemandeDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference", models.CharField(editable=False, max_length=30, unique=True)),
                ("type", models.CharField(choices=[("certificat", "Certificat de scolarité"), ("releve", "Relevé de notes"), ("carte", "Carte d'étudiant")], max_length=20)),
                ("nombre", models.PositiveSmallIntegerField(default=1, help_text="Nombre d'exemplaires")),
                ("motif", models.CharField(blank=True, default="", help_text="Usage prévu (banque, stage, visa…)", max_length=255)),
                ("statut", models.CharField(choices=[("en_attente", "En attente"), ("prete", "Prêt à retirer"), ("remise", "Remis"), ("rejetee", "Rejetée")], default="en_attente", max_length=20)),
                ("reponse", models.CharField(blank=True, default="", help_text="Message de l'administration (motif de rejet, consignes de retrait…)", max_length=255)),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("traite_le", models.DateTimeField(blank=True, null=True)),
                ("remise_le", models.DateTimeField(blank=True, null=True)),
                ("annee_academique", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="demandes_documents", to="academique.anneeacademique")),
                ("document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="demandes", to="attestations.documentdelivre")),
                ("etudiant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="demandes_documents", to="etudiants.etudiant")),
                ("traite_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="demandes_documents_traitees", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-cree_le", "-id"], "indexes": [models.Index(fields=["statut", "type"], name="attestation_statut_98f2b5_idx")]},
        ),
    ]

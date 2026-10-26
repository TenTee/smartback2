import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("categorie", models.CharField(choices=[("finance", "Finances"), ("etudiants", "Étudiants"), ("pedagogie", "Pédagogie"), ("systeme", "Système")], max_length=20)),
                ("type", models.CharField(help_text="Code de l'événement, ex. paiement_recu", max_length=50)),
                ("titre", models.CharField(max_length=200)),
                ("message", models.TextField(blank=True, default="")),
                ("lien", models.CharField(blank=True, default="", help_text="Page de l'application à ouvrir", max_length=300)),
                ("niveau", models.CharField(choices=[("info", "Information"), ("succes", "Succès"), ("alerte", "Alerte"), ("urgent", "Urgent")], default="info", max_length=10)),
                ("cle", models.CharField(blank=True, default="", help_text="Évite les doublons (rappels périodiques)", max_length=150)),
                ("lu", models.BooleanField(default=False)),
                ("lu_le", models.DateTimeField(blank=True, null=True)),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("destinataire", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-cree_le"]},
        ),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["destinataire", "lu"], name="notificatio_destina_353850_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["destinataire", "cle"], name="notificatio_destina_251ea3_idx")),
        migrations.CreateModel(
            name="AbonnementPush",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("navigateur", models.CharField(blank=True, default="", max_length=255)),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("dernier_envoi", models.DateTimeField(blank=True, null=True)),
                ("utilisateur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="abonnements_push", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="PreferenceNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("categories_desactivees", models.JSONField(blank=True, default=list)),
                ("push_actif", models.BooleanField(default=True)),
                ("utilisateur", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="preference_notifications", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

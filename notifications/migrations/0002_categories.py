from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="categorie",
            field=models.CharField(choices=[("finance", "Finances"), ("etudiants", "Étudiants"), ("pedagogie", "Pédagogie"), ("etudiant", "Ma scolarité"), ("enseignement", "Mes cours"), ("messages", "Messages"), ("systeme", "Système")], max_length=20),
        ),
    ]

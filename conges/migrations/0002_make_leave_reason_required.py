from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conges", "0001_initial"),
        ("personnels", "0004_leave_balance_and_extra_days"),
    ]

    operations = [
        migrations.AlterField(
            model_name="conge",
            name="raison",
            field=models.TextField(),
        ),
    ]
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tns_api", "0015_claim_approval_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("EMPLOYEE", "Employee"),
                    ("APPROVER", "Approver"),
                    ("ADMIN", "System Administrator"),
                    ("SUPERUSER", "Super User"),
                ],
                default="EMPLOYEE",
                max_length=20,
            ),
        ),
    ]

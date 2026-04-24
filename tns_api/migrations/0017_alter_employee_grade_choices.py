from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tns_api", "0016_alter_userprofile_role_add_superuser"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="grade",
            field=models.CharField(
                choices=[
                    (1, "One"),
                    (2, "Two"),
                    (3, "Three"),
                    (4, "Four"),
                    (5, "Five"),
                    (6, "Six"),
                    (7, "Seven"),
                    (8, "Eight"),
                    (9, "Nine"),
                    (10, "Ten"),
                    (11, "Eleven"),
                    (12, "Twelve"),
                ],
                default=1,
                max_length=2,
            ),
        ),
    ]

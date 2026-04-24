from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tns_api", "0017_alter_employee_grade_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowance",
            name="nature",
            field=models.CharField(
                blank=True,
                choices=[
                    ("OUT_OF_STATION", "Out of Station"),
                    ("FUEL", "Fuel"),
                    ("BREAKFAST", "Breakfast"),
                    ("LUNCH", "Lunch"),
                    ("DINNER", "Dinner"),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]

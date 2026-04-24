from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tns_api", "0018_allowance_nature"),
    ]

    operations = [
        migrations.AddField(
            model_name="allowance",
            name="grade_range",
            field=models.CharField(
                blank=True,
                choices=[
                    ("LOWER", "Lower"),
                    ("MIDDLE", "Middle"),
                    ("UPPER", "Upper"),
                ],
                max_length=10,
                null=True,
            ),
        ),
    ]

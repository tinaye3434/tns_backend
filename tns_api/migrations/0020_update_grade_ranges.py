from django.db import migrations, models


def remap_grades_and_allowance_ranges(apps, schema_editor):
    Employee = apps.get_model("tns_api", "Employee")
    Allowance = apps.get_model("tns_api", "Allowance")

    Employee.objects.filter(grade="12").update(grade="11")

    Allowance.objects.filter(grade_range="LOWER").update(grade_range="GENERAL")
    Allowance.objects.filter(grade_range="MIDDLE").update(grade_range="GENERAL")
    Allowance.objects.filter(grade_range="UPPER").update(grade_range="MANAGEMENT")


class Migration(migrations.Migration):

    dependencies = [
        ("tns_api", "0019_allowance_grade_range"),
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
                ],
                default=1,
                max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="allowance",
            name="grade_range",
            field=models.CharField(
                blank=True,
                choices=[
                    ("GENERAL", "General"),
                    ("MANAGEMENT", "Management"),
                    ("HODS_AND_COUNCILORS", "HODs and Other Councilors"),
                    ("CEO_AND_COUNCIL_CHAIR", "CEO and Council Chair"),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.RunPython(remap_grades_and_allowance_ranges, migrations.RunPython.noop),
    ]

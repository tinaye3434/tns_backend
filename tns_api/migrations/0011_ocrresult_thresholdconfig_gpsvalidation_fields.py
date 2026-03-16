from django.db import migrations, models
import django.db.models.deletion


def seed_thresholds(apps, schema_editor):
    ThresholdConfig = apps.get_model("tns_api", "ThresholdConfig")
    ThresholdConfig.objects.get_or_create(
        key="GPS_VARIANCE_THRESHOLD",
        defaults={
            "value": 0.15,
            "unit": "percent",
            "description": "Max allowed variance between claimed and system distance.",
        },
    )


def unseed_thresholds(apps, schema_editor):
    ThresholdConfig = apps.get_model("tns_api", "ThresholdConfig")
    ThresholdConfig.objects.filter(key="GPS_VARIANCE_THRESHOLD").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tns_api", "0010_claim_actual_mileage"),
    ]

    operations = [
        migrations.CreateModel(
            name="OCRResult",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vendor_name", models.CharField(blank=True, max_length=255)),
                ("receipt_date", models.DateField(blank=True, null=True)),
                ("total_amount", models.FloatField(blank=True, null=True)),
                ("tax_amount", models.FloatField(blank=True, null=True)),
                ("receipt_number", models.CharField(blank=True, max_length=100)),
                ("match_status", models.CharField(default="pending", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("raw_text", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "receipt",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ocr_result",
                        to="tns_api.receipt",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ThresholdConfig",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=100, unique=True)),
                ("value", models.FloatField()),
                ("unit", models.CharField(blank=True, max_length=50)),
                ("description", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["key"],
            },
        ),
        migrations.AddField(
            model_name="gpsvalidation",
            name="claimed_distance_km",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gpsvalidation",
            name="variance_km",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gpsvalidation",
            name="variance_pct",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="gpsvalidation",
            name="threshold_pct",
            field=models.FloatField(default=0.15),
        ),
        migrations.AddField(
            model_name="gpsvalidation",
            name="status",
            field=models.CharField(default="pending", max_length=20),
        ),
        migrations.RunPython(seed_thresholds, reverse_code=unseed_thresholds),
    ]

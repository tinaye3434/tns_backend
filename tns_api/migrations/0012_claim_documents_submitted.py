from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tns_api', '0011_ocrresult_thresholdconfig_gpsvalidation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='claim',
            name='documents_submitted',
            field=models.BooleanField(default=False),
        ),
    ]

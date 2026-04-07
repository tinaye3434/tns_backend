from django.db import migrations, models


def forwards(apps, schema_editor):
    Claim = apps.get_model('tns_api', 'Claim')
    for claim in Claim.objects.all():
        raw = str(getattr(claim, 'status', '1'))
        if raw == '0':
            claim.approval_status = 'rejected'
        else:
            claim.approval_status = 'pending'
        claim.save(update_fields=['approval_status'])


def backwards(apps, schema_editor):
    Claim = apps.get_model('tns_api', 'Claim')
    for claim in Claim.objects.all():
        status_value = '1'
        if getattr(claim, 'approval_status', '') == 'rejected':
            status_value = '0'
        claim.status = status_value
        claim.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('tns_api', '0014_fraud_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='claim',
            name='approval_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='claim',
            name='status',
        ),
    ]

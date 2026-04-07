from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tns_api', '0013_alter_ocrresult_id_alter_thresholdconfig_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='FraudModelSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('model_blob', models.BinaryField()),
                ('feature_columns', models.JSONField(blank=True, default=list)),
                ('feature_means', models.JSONField(blank=True, default=list)),
                ('feature_stds', models.JSONField(blank=True, default=list)),
                ('score_p05', models.FloatField(default=0.0)),
                ('score_p95', models.FloatField(default=1.0)),
                ('training_rows', models.IntegerField(default=0)),
                ('trained_from', models.DateTimeField(blank=True, null=True)),
                ('trained_to', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='FraudScore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('score', models.FloatField()),
                ('raw_score', models.FloatField()),
                ('risk_level', models.CharField(default='medium', max_length=10)),
                ('features', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('claim', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='fraud_score', to='tns_api.claim')),
                ('model_snapshot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='scores', to='tns_api.fraudmodelsnapshot')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
    ]

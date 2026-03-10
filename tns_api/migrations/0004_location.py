from django.db import migrations, models


LOCATIONS = [
    {"name": "Beitbridge", "longitude": 30.0000, "latitude": -22.2167},
    {"name": "Bindura", "longitude": 31.3333, "latitude": -17.3000},
    {"name": "Binga", "longitude": 27.3333, "latitude": -17.6167},
    {"name": "Birchenough Bridge", "longitude": 32.0170, "latitude": -20.1660},
    {"name": "Bulawayo", "longitude": 28.5833, "latitude": -20.1500},
    {"name": "Chegutu", "longitude": 30.1333, "latitude": -18.1333},
    {"name": "Chimanimani", "longitude": 32.8667, "latitude": -19.8000},
    {"name": "Chinhoyi", "longitude": 30.2000, "latitude": -17.3500},
    {"name": "Chipinge", "longitude": 32.6167, "latitude": -20.2000},
    {"name": "Chiredzi", "longitude": 31.6667, "latitude": -21.0500},
    {"name": "Chirundu", "longitude": 28.8500, "latitude": -16.0333},
    {"name": "Chitungwiza", "longitude": 31.0756, "latitude": -18.0127},
    {"name": "Dete", "longitude": 26.8667, "latitude": -18.6167},
    {"name": "Epworth", "longitude": 31.1475, "latitude": -17.8900},
    {"name": "Esigodini", "longitude": 28.9333, "latitude": -20.2833},
    {"name": "Gokwe", "longitude": 28.9333, "latitude": -18.2167},
    {"name": "Gwanda", "longitude": 29.0000, "latitude": -20.9333},
    {"name": "Gweru", "longitude": 29.8167, "latitude": -19.4500},
    {"name": "Harare", "longitude": 31.0530, "latitude": -17.8292},
    {"name": "Headlands", "longitude": 31.7333, "latitude": -18.2833},
    {"name": "Hwange", "longitude": 26.5000, "latitude": -18.3667},
    {"name": "Inyathi", "longitude": 28.6500, "latitude": -19.6667},
    {"name": "Kadoma", "longitude": 29.9167, "latitude": -18.3333},
    {"name": "Kariba", "longitude": 28.8000, "latitude": -16.5167},
    {"name": "Karoi", "longitude": 29.7000, "latitude": -16.8167},
    {"name": "Kwekwe", "longitude": 29.8000, "latitude": -18.9167},
    {"name": "Lupane", "longitude": 27.8000, "latitude": -18.9333},
    {"name": "Macheke", "longitude": 31.8500, "latitude": -18.1333},
    {"name": "Marondera", "longitude": 31.5500, "latitude": -18.1833},
    {"name": "Masvingo", "longitude": 30.8333, "latitude": -20.0667},
    {"name": "Mazowe", "longitude": 30.9667, "latitude": -17.5167},
    {"name": "Mhangura", "longitude": 30.1667, "latitude": -16.9000},
    {"name": "Mhangura Mine", "longitude": 30.1550, "latitude": -16.9030},
    {"name": "Mount Darwin", "longitude": 31.5833, "latitude": -16.7833},
    {"name": "Murehwa", "longitude": 31.7833, "latitude": -17.6500},
    {"name": "Mvurwi", "longitude": 30.8500, "latitude": -17.0333},
    {"name": "Mutare", "longitude": 32.6667, "latitude": -18.9667},
    {"name": "Mutoko", "longitude": 32.2167, "latitude": -17.4000},
    {"name": "Norton", "longitude": 30.7000, "latitude": -17.8833},
    {"name": "Nyanga", "longitude": 32.7500, "latitude": -18.2167},
    {"name": "Plumtree", "longitude": 27.8167, "latitude": -20.4833},
    {"name": "Redcliff", "longitude": 29.7833, "latitude": -19.0333},
    {"name": "Ruwa", "longitude": 31.2440, "latitude": -17.8897},
    {"name": "Rusape", "longitude": 32.1167, "latitude": -18.5333},
    {"name": "Shamva", "longitude": 31.5667, "latitude": -17.3167},
    {"name": "Shurugwi", "longitude": 30.0000, "latitude": -19.6667},
    {"name": "Triangle", "longitude": 31.0167, "latitude": -20.1833},
    {"name": "Victoria Falls", "longitude": 25.8553, "latitude": -17.9243},
    {"name": "Zvishavane", "longitude": 30.0667, "latitude": -20.3333},
]


def seed_locations(apps, schema_editor):
    Location = apps.get_model('tns_api', 'Location')
    Location.objects.bulk_create([Location(**item) for item in LOCATIONS], ignore_conflicts=True)


def remove_locations(apps, schema_editor):
    Location = apps.get_model('tns_api', 'Location')
    Location.objects.filter(name__in=[item['name'] for item in LOCATIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tns_api', '0003_rename_distance_full_claim_calculated_distance_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('longitude', models.FloatField()),
                ('latitude', models.FloatField()),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(seed_locations, remove_locations),
    ]

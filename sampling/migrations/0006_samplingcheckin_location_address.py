from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sampling", "0005_clear_amap_site_coordinates"),
    ]

    operations = [
        migrations.AddField(
            model_name="samplingcheckin",
            name="location_address",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]

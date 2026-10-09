from django.db import migrations, models


def clear_cached_site_coordinates(apps, schema_editor):
    SamplingTask = apps.get_model("sampling", "SamplingTask")
    SamplingTask.objects.update(
        site_longitude=None,
        site_latitude=None,
        site_geocoded_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sampling", "0007_reset_site_geocoding_for_geocoder"),
    ]

    operations = [
        migrations.AddField(
            model_name="samplingtask",
            name="site_city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="samplingcheckin",
            name="location_city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="samplingcheckin",
            name="status",
            field=models.CharField(choices=[
                ("in_range", "原范围内打卡"),
                ("outside", "原范围外异常打卡"),
                ("same_city", "收货地市内打卡"),
                ("outside_city", "跨市异常打卡"),
                ("unavailable", "定位异常打卡"),
            ], max_length=16),
        ),
        migrations.RunPython(clear_cached_site_coordinates, migrations.RunPython.noop),
    ]

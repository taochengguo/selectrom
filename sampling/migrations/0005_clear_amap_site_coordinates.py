from django.db import migrations


def clear_amap_coordinates(apps, schema_editor):
    SamplingTask = apps.get_model("sampling", "SamplingTask")
    SamplingTask.objects.filter(site_geocoded_at__isnull=False).update(
        site_longitude=None,
        site_latitude=None,
        site_geocoded_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sampling", "0004_samplingcheckin_created_by"),
    ]

    operations = [migrations.RunPython(clear_amap_coordinates, migrations.RunPython.noop)]

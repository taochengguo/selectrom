from django.db import migrations


def clear_search_coordinates(apps, schema_editor):
    SamplingTask = apps.get_model("sampling", "SamplingTask")
    SamplingTask.objects.filter(site_geocoded_at__isnull=False).update(
        site_longitude=None,
        site_latitude=None,
        site_geocoded_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sampling", "0006_samplingcheckin_location_address"),
    ]

    operations = [migrations.RunPython(clear_search_coordinates, migrations.RunPython.noop)]

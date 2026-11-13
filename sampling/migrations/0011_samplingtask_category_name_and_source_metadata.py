from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sampling', '0010_samplingtask_detailed_address_and_more')]
    operations = [
        migrations.AddField(model_name='samplingtask', name='category_name', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='samplingtask', name='source_metadata', field=models.JSONField(blank=True, default=dict)),
    ]

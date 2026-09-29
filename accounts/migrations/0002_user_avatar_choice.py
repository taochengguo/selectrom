from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar_choice",
            field=models.CharField(
                choices=[
                    ("icon1", "头像 1"),
                    ("icon2", "头像 2"),
                    ("icon3", "头像 3"),
                    ("icon4", "头像 4"),
                    ("icon5", "头像 5"),
                ],
                default="icon1",
                max_length=5,
            ),
        ),
    ]

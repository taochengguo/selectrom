from django.db import migrations


def consolidate_names(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    users = User.objects.using(schema_editor.connection.alias)
    updates = []
    for user in users.all():
        name = ' '.join(part.strip() for part in (user.first_name, user.last_name) if part.strip())
        if len(name) > 150:
            raise ValueError(f'User {user.pk}: combined name exceeds 150 characters; manual correction required')
        if name != user.first_name or user.last_name:
            updates.append((user.pk, name))
    for pk, name in updates:
        users.filter(pk=pk).update(first_name=name, last_name='')


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_user_avatar_choice')]
    operations = [
        migrations.RunPython(consolidate_names, migrations.RunPython.noop),
        migrations.RemoveField(model_name='user', name='phone'),
    ]

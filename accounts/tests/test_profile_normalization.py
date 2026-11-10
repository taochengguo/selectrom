from importlib import import_module
from django.apps import apps
from django.test import TestCase
from accounts.models import User
from sampling.management_views import AdminUserEditForm


class UserProfileNormalizationTests(TestCase):
    def test_existing_split_name_is_preserved_and_migration_is_idempotent(self):
        user = User.objects.create_user('legacy', role='sampler', first_name='  立温 ', last_name=' 戴 ')
        migrate = import_module('accounts.migrations.0003_normalize_user_profile').consolidate_names
        from django.db import connection
        editor = connection.schema_editor(atomic=False)
        migrate(apps, editor)
        migrate(apps, editor)
        user.refresh_from_db()
        self.assertEqual(user.first_name, '立温 戴')
        self.assertEqual(user.last_name, '')
        self.assertEqual(user.get_full_name(), '立温 戴')

    def test_edit_form_ignores_retired_profile_fields(self):
        user = User.objects.create_user('member', role='sampler', first_name='张三')
        form = AdminUserEditForm({'username':'member','first_name':'李四','role':'sampler','is_active':'on','phone':'123','last_name':'旧姓'}, instance=user)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.first_name, '李四')
        self.assertEqual(user.last_name, '')
        self.assertNotIn('phone', {field.name for field in User._meta.fields})

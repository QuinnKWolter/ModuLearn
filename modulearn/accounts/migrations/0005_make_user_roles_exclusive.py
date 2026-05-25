from django.db import migrations


def make_roles_exclusive(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_instructor=True, is_student=True).update(is_student=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_alter_user_kt_login_alter_user_kt_user_id"),
    ]

    operations = [
        migrations.RunPython(make_roles_exclusive, migrations.RunPython.noop),
    ]

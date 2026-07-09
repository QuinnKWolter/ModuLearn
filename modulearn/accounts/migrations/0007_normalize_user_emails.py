from django.db import migrations


def normalize_user_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.exclude(email="").only("id", "email").iterator():
        normalized = (user.email or "").strip().casefold()
        if normalized != user.email:
            User.objects.filter(pk=user.pk).update(email=normalized)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_user_is_anonymous_participant"),
    ]

    operations = [
        migrations.RunPython(normalize_user_emails, migrations.RunPython.noop),
    ]

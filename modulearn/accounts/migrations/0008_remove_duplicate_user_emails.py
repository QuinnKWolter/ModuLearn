from collections import defaultdict

from django.db import migrations


def remove_duplicate_user_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    by_email = defaultdict(list)

    for user in User.objects.exclude(email="").order_by("id").iterator():
        normalized = (user.email or "").strip().casefold()
        if normalized != user.email:
            User.objects.filter(pk=user.pk).update(email=normalized)
            user.email = normalized
        if normalized:
            by_email[normalized].append(user.pk)

    for user_ids in by_email.values():
        if len(user_ids) <= 1:
            continue
        User.objects.filter(pk__in=user_ids[1:]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_normalize_user_emails"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_user_emails, migrations.RunPython.noop),
    ]

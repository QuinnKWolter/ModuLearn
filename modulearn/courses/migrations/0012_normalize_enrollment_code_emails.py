from django.db import migrations


def normalize_enrollment_code_emails(apps, schema_editor):
    EnrollmentCode = apps.get_model("courses", "EnrollmentCode")
    keepers = {}

    for invitation in EnrollmentCode.objects.order_by("course_instance_id", "id").iterator():
        normalized = (invitation.email or "").strip().casefold()
        key = (invitation.course_instance_id, normalized)
        keeper = keepers.get(key)

        if keeper is not None:
            if invitation.used and not keeper.used:
                EnrollmentCode.objects.filter(pk=keeper.pk).update(used=True)
                keeper.used = True
            invitation.delete()
            continue

        if normalized != invitation.email:
            EnrollmentCode.objects.filter(pk=invitation.pk).update(email=normalized)
            invitation.email = normalized
        keepers[key] = invitation


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0011_adaptive_branching"),
    ]

    operations = [
        migrations.RunPython(normalize_enrollment_code_emails, migrations.RunPython.noop),
    ]

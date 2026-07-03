# Generated manually for Prolific SESSION_ID idempotency.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0002_rename_recruitment_status_entered_idx_recruitment_status_887633_idx_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="participantsession",
            name="uniq_participant_session_per_source_pid",
        ),
        migrations.AddIndex(
            model_name="participantsession",
            index=models.Index(fields=["recruitment_source", "external_pid"], name="recruitment_source_pid_idx"),
        ),
        migrations.AddConstraint(
            model_name="participantsession",
            constraint=models.UniqueConstraint(
                condition=~models.Q(external_session_id=""),
                fields=("recruitment_source", "external_session_id"),
                name="uniq_participant_session_per_source_ext_session",
            ),
        ),
    ]

# Generated manually for ModuLearn recruitment scaffolding.

import uuid
import django.db.models.deletion
import recruitment.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("courses", "0006_course_is_locked_for_research"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RecruitmentSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform", models.CharField(choices=[("prolific", "Prolific"), ("sona", "SONA")], max_length=16)),
                ("label", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("max_participants", models.PositiveIntegerField(blank=True, null=True)),
                ("condition_strategy", models.CharField(choices=[("hash", "Hash-based"), ("balanced", "Balanced counter"), ("schedule", "Preallocated schedule")], default="hash", max_length=16)),
                ("condition_labels", models.CharField(blank=True, help_text="Comma-separated condition names, e.g. control,treatment.", max_length=255)),
                ("prolific_study_id", models.CharField(blank=True, max_length=64)),
                ("prolific_completion_code_complete", models.CharField(blank=True, max_length=32)),
                ("prolific_completion_code_screened_out", models.CharField(blank=True, max_length=32)),
                ("prolific_completion_code_attention_failed", models.CharField(blank=True, max_length=32)),
                ("prolific_use_secured_url", models.BooleanField(default=False)),
                ("sona_base_url", models.URLField(blank=True)),
                ("sona_experiment_id", models.CharField(blank=True, max_length=32)),
                ("sona_credit_token", recruitment.fields.EncryptedCharField(blank=True, help_text="Sensitive SONA credit token. Treat as a server secret.", max_length=512)),
                ("sona_grant_server_side", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("course_instance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recruitment_sources", to="courses.courseinstance")),
            ],
            options={
                "ordering": ["course_instance_id", "platform", "id"],
            },
        ),
        migrations.CreateModel(
            name="ParticipantSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("external_pid", models.CharField(db_index=True, max_length=64)),
                ("external_study_id", models.CharField(blank=True, max_length=64)),
                ("external_session_id", models.CharField(blank=True, max_length=64)),
                ("condition", models.CharField(blank=True, max_length=32)),
                ("status", models.CharField(choices=[("entered", "Entered"), ("consented", "Consented"), ("in_progress", "In progress"), ("completed", "Completed"), ("screened_out", "Screened out"), ("attention_failed", "Attention check failed"), ("abandoned", "Abandoned"), ("rejected", "Rejected (verification failed)")], default="entered", max_length=32)),
                ("raw_query_string", models.TextField(blank=True)),
                ("referer", models.TextField(blank=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("entered_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("completion_code_used", models.CharField(blank=True, max_length=32)),
                ("completion_metadata", models.JSONField(blank=True, default=dict)),
                ("enrollment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="participant_sessions", to="courses.enrollment")),
                ("recruitment_source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="participant_sessions", to="recruitment.recruitmentsource")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recruitment_sessions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-entered_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="RecruitmentEntryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform_detected", models.CharField(blank=True, max_length=16)),
                ("external_pid", models.CharField(blank=True, max_length=64)),
                ("raw_query_string", models.TextField(blank=True)),
                ("referer", models.TextField(blank=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("accepted", models.BooleanField(default=False)),
                ("rejection_reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("participant_session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entry_logs", to="recruitment.participantsession")),
                ("source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="entry_logs", to="recruitment.recruitmentsource")),
            ],
            options={
                "ordering": ["-created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="RecruitmentAssignmentSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slot_index", models.PositiveIntegerField()),
                ("condition", models.CharField(max_length=32)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("claimed_by", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assignment_slot", to="recruitment.participantsession")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_slots", to="recruitment.recruitmentsource")),
            ],
            options={
                "ordering": ["source_id", "slot_index"],
            },
        ),
        migrations.AddConstraint(
            model_name="recruitmentsource",
            constraint=models.UniqueConstraint(fields=("course_instance", "platform"), name="uniq_recruitment_source_per_instance_platform"),
        ),
        migrations.AddConstraint(
            model_name="participantsession",
            constraint=models.UniqueConstraint(fields=("recruitment_source", "external_pid"), name="uniq_participant_session_per_source_pid"),
        ),
        migrations.AddIndex(
            model_name="participantsession",
            index=models.Index(fields=["status", "entered_at"], name="recruitment_status_entered_idx"),
        ),
        migrations.AddIndex(
            model_name="participantsession",
            index=models.Index(fields=["condition"], name="recruitment_condition_idx"),
        ),
        migrations.AddConstraint(
            model_name="recruitmentassignmentslot",
            constraint=models.UniqueConstraint(fields=("source", "slot_index"), name="uniq_recruitment_assignment_slot"),
        ),
    ]

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from courses.models import CourseInstance, Enrollment
from .fields import EncryptedCharField


class RecruitmentSource(models.Model):
    PLATFORM_PROLIFIC = "prolific"
    PLATFORM_SONA = "sona"
    PLATFORM_CHOICES = [
        (PLATFORM_PROLIFIC, "Prolific"),
        (PLATFORM_SONA, "SONA"),
    ]

    CONDITION_HASH = "hash"
    CONDITION_BALANCED = "balanced"
    CONDITION_SCHEDULE = "schedule"
    CONDITION_STRATEGY_CHOICES = [
        (CONDITION_HASH, "Hash-based"),
        (CONDITION_BALANCED, "Balanced counter"),
        (CONDITION_SCHEDULE, "Preallocated schedule"),
    ]

    course_instance = models.ForeignKey(
        CourseInstance,
        on_delete=models.CASCADE,
        related_name="recruitment_sources",
    )
    platform = models.CharField(max_length=16, choices=PLATFORM_CHOICES)
    label = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)

    condition_strategy = models.CharField(
        max_length=16,
        choices=CONDITION_STRATEGY_CHOICES,
        default=CONDITION_HASH,
    )
    condition_labels = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated condition names, e.g. control,treatment.",
    )

    prolific_study_id = models.CharField(max_length=64, blank=True)
    prolific_completion_code_complete = models.CharField(max_length=32, blank=True)
    prolific_completion_code_screened_out = models.CharField(max_length=32, blank=True)
    prolific_completion_code_attention_failed = models.CharField(max_length=32, blank=True)
    prolific_use_secured_url = models.BooleanField(default=False)

    sona_base_url = models.URLField(blank=True)
    sona_experiment_id = models.CharField(max_length=32, blank=True)
    sona_credit_token = EncryptedCharField(
        max_length=512,
        blank=True,
        help_text="Sensitive SONA credit token. Treat as a server secret.",
    )
    sona_grant_server_side = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course_instance", "platform"],
                name="uniq_recruitment_source_per_instance_platform",
            )
        ]
        ordering = ["course_instance_id", "platform", "id"]

    def __str__(self):
        label = self.label or self.get_platform_display()
        return f"{label} for {self.course_instance}"

    @property
    def conditions(self) -> list[str]:
        labels = [item.strip() for item in (self.condition_labels or "").split(",") if item.strip()]
        return labels or ["default"]

    def participant_count(self) -> int:
        return self.participant_sessions.exclude(status=ParticipantSession.STATUS_REJECTED).count()

    def has_capacity(self) -> bool:
        return self.max_participants is None or self.participant_count() < self.max_participants


class RecruitmentAssignmentSlot(models.Model):
    source = models.ForeignKey(
        RecruitmentSource,
        on_delete=models.CASCADE,
        related_name="assignment_slots",
    )
    slot_index = models.PositiveIntegerField()
    condition = models.CharField(max_length=32)
    claimed_by = models.OneToOneField(
        "ParticipantSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_slot",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "slot_index"], name="uniq_recruitment_assignment_slot"),
        ]
        ordering = ["source_id", "slot_index"]

    def __str__(self):
        return f"{self.source_id} slot {self.slot_index}: {self.condition}"


class ParticipantSession(models.Model):
    STATUS_ENTERED = "entered"
    STATUS_CONSENTED = "consented"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_SCREENED_OUT = "screened_out"
    STATUS_ATTENTION_FAILED = "attention_failed"
    STATUS_ABANDONED = "abandoned"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_ENTERED, "Entered"),
        (STATUS_CONSENTED, "Consented"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_SCREENED_OUT, "Screened out"),
        (STATUS_ATTENTION_FAILED, "Attention check failed"),
        (STATUS_ABANDONED, "Abandoned"),
        (STATUS_REJECTED, "Rejected (verification failed)"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    recruitment_source = models.ForeignKey(
        RecruitmentSource,
        on_delete=models.PROTECT,
        related_name="participant_sessions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recruitment_sessions",
    )
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participant_sessions",
    )

    external_pid = models.CharField(max_length=64, db_index=True)
    external_study_id = models.CharField(max_length=64, blank=True)
    external_session_id = models.CharField(max_length=64, blank=True)
    condition = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_ENTERED)

    raw_query_string = models.TextField(blank=True)
    referer = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    entered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_code_used = models.CharField(max_length=32, blank=True)
    completion_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recruitment_source", "external_session_id"],
                condition=~Q(external_session_id=""),
                name="uniq_participant_session_per_source_ext_session",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "entered_at"]),
            models.Index(fields=["condition"]),
            models.Index(fields=["recruitment_source", "external_pid"], name="recruitment_source_pid_idx"),
        ]
        ordering = ["-entered_at", "id"]

    def __str__(self):
        return f"{self.recruitment_source.platform}:{self.external_pid}"

    @property
    def is_finished(self) -> bool:
        return self.status in {
            self.STATUS_COMPLETED,
            self.STATUS_SCREENED_OUT,
            self.STATUS_ATTENTION_FAILED,
        }

    def mark_complete(self, status: str, *, code: str = "", metadata: dict | None = None):
        self.status = status
        self.completed_at = self.completed_at or timezone.now()
        self.completion_code_used = code or self.completion_code_used
        if metadata:
            current = self.completion_metadata or {}
            current.update(metadata)
            self.completion_metadata = current


class RecruitmentEntryLog(models.Model):
    source = models.ForeignKey(
        RecruitmentSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entry_logs",
    )
    participant_session = models.ForeignKey(
        ParticipantSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entry_logs",
    )
    platform_detected = models.CharField(max_length=16, blank=True)
    external_pid = models.CharField(max_length=64, blank=True)
    raw_query_string = models.TextField(blank=True)
    referer = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    accepted = models.BooleanField(default=False)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]

    def __str__(self):
        state = "accepted" if self.accepted else "rejected"
        return f"{state} entry {self.platform_detected}:{self.external_pid}"

from django.contrib import admin

from .models import ParticipantSession, RecruitmentAssignmentSlot, RecruitmentEntryLog, RecruitmentSource


@admin.register(RecruitmentSource)
class RecruitmentSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "course_instance", "platform", "label", "is_active", "max_participants", "condition_strategy", "created_at")
    list_filter = ("platform", "is_active", "condition_strategy")
    search_fields = ("label", "course_instance__group_name", "course_instance__course__title", "prolific_study_id", "sona_experiment_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ParticipantSession)
class ParticipantSessionAdmin(admin.ModelAdmin):
    list_display = ("uuid", "recruitment_source", "external_pid", "condition", "status", "entered_at", "completed_at")
    list_filter = ("status", "condition", "recruitment_source__platform")
    search_fields = ("uuid", "external_pid", "external_study_id", "external_session_id", "user__username")
    readonly_fields = ("uuid", "entered_at", "updated_at")


@admin.register(RecruitmentAssignmentSlot)
class RecruitmentAssignmentSlotAdmin(admin.ModelAdmin):
    list_display = ("source", "slot_index", "condition", "claimed_by", "claimed_at")
    list_filter = ("condition", "source")
    search_fields = ("condition", "claimed_by__external_pid")


@admin.register(RecruitmentEntryLog)
class RecruitmentEntryLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "platform_detected", "external_pid", "accepted", "rejection_reason")
    list_filter = ("accepted", "platform_detected")
    search_fields = ("external_pid", "raw_query_string", "rejection_reason")
    readonly_fields = ("created_at",)

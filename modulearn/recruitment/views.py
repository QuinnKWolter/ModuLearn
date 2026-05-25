from __future__ import annotations

import csv
import hashlib

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from courses.models import CourseProgress, Enrollment
from recruitment.models import ParticipantSession, RecruitmentEntryLog, RecruitmentSource
from recruitment.services.conditions import assign_condition
from recruitment.services.prolific import ProlificIds, ProlificVerificationError, completion_url, verify_secured_url, verify_submission_api
from recruitment.services.sona import SonaCreditError, client_credit_url, grant_credit_server_side

User = get_user_model()


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _entry_log_kwargs(request, source=None, platform="", external_pid=""):
    return {
        "source": source,
        "platform_detected": platform,
        "external_pid": external_pid or "",
        "raw_query_string": request.META.get("QUERY_STRING", ""),
        "referer": request.META.get("HTTP_REFERER", ""),
        "ip_address": _client_ip(request),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
    }


def _rate_limit_entry(request, source_id: int) -> bool:
    ip = _client_ip(request) or "unknown"
    digest = hashlib.sha256(f"{source_id}:{ip}".encode("utf-8")).hexdigest()
    key = f"recruitment:enter:{digest}"
    count = cache.get(key, 0) + 1
    cache.set(key, count, 60)
    return count <= 30


def _detect_platform(request):
    prolific_pid = request.GET.get("PROLIFIC_PID") or request.GET.get("prolific_pid")
    sona_id = request.GET.get("sona_id") or request.GET.get("id") or request.GET.get("SURVEY_CODE")
    if prolific_pid:
        return RecruitmentSource.PLATFORM_PROLIFIC, prolific_pid
    if sona_id:
        return RecruitmentSource.PLATFORM_SONA, sona_id
    return "", ""


def _participant_username(platform: str, source_id: int, external_pid: str) -> str:
    digest = hashlib.sha256(f"{platform}:{source_id}:{external_pid}".encode("utf-8")).hexdigest()[:16]
    return f"participant_{platform}_{digest}"[:150]


def _provision_participant_user(source: RecruitmentSource, external_pid: str):
    username = _participant_username(source.platform, source.id, external_pid)
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "is_student": True,
            "is_instructor": False,
            "is_anonymous_participant": True,
            "first_name": source.platform.title(),
            "last_name": external_pid[:64],
            "email": "",
        },
    )
    changed = []
    if created or user.has_usable_password():
        user.set_unusable_password()
        changed.append("password")
    if not getattr(user, "is_student", False):
        user.is_student = True
        changed.append("is_student")
    if getattr(user, "is_instructor", False):
        user.is_instructor = False
        changed.append("is_instructor")
    if not getattr(user, "is_anonymous_participant", False):
        user.is_anonymous_participant = True
        changed.append("is_anonymous_participant")
    if changed:
        user.save()
    return user


def _verify_entry(request, source: RecruitmentSource, platform: str, external_pid: str) -> dict:
    if platform == RecruitmentSource.PLATFORM_PROLIFIC:
        ids = ProlificIds(
            pid=external_pid,
            study_id=request.GET.get("STUDY_ID", ""),
            session_id=request.GET.get("SESSION_ID", ""),
        )
        if source.prolific_study_id and ids.study_id and source.prolific_study_id != ids.study_id:
            raise ProlificVerificationError("This Prolific study id does not match the recruitment source.")
        if source.prolific_use_secured_url:
            return {"secured_url": verify_secured_url(request.GET.get("prolific_token", ""), ids)}
        try:
            return {"submission_api": verify_submission_api(ids)}
        except ProlificVerificationError:
            raise
        except Exception as exc:
            return {"submission_api": {"verified": False, "reason": str(exc)}}
    return {"verified": platform == RecruitmentSource.PLATFORM_SONA}


@require_http_methods(["GET"])
def enter(request, source_id):
    source = get_object_or_404(RecruitmentSource.objects.select_related("course_instance", "course_instance__course"), id=source_id)
    platform, external_pid = _detect_platform(request)
    log_data = _entry_log_kwargs(request, source=source, platform=platform, external_pid=external_pid)

    def reject(reason, status=400):
        RecruitmentEntryLog.objects.create(**log_data, accepted=False, rejection_reason=reason[:255])
        return render(request, "recruitment/ineligible.html", {"source": source, "reason": reason}, status=status)

    if not _rate_limit_entry(request, source.id):
        return reject("Too many recruitment entry attempts. Please wait a minute and try again.", 429)
    if not source.is_active:
        return reject("This recruitment link is no longer active.", 403)
    if not platform or not external_pid:
        return reject("Missing participant identifier.")
    if platform != source.platform:
        return reject("This participant link does not match the configured recruitment platform.")
    if not source.has_capacity():
        return reject("This study has reached its participant cap.", 403)

    try:
        verification_metadata = _verify_entry(request, source, platform, external_pid)
    except ProlificVerificationError as exc:
        return reject(str(exc), 403)

    with transaction.atomic():
        user = _provision_participant_user(source, external_pid)
        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course_instance=source.course_instance,
            defaults={"active": True},
        )
        if not enrollment.active:
            enrollment.active = True
            enrollment.save(update_fields=["active"])

        session_defaults = {
            "user": user,
            "enrollment": enrollment,
            "external_study_id": request.GET.get("STUDY_ID", ""),
            "external_session_id": request.GET.get("SESSION_ID", ""),
            "raw_query_string": log_data["raw_query_string"],
            "referer": log_data["referer"],
            "ip_address": log_data["ip_address"],
            "user_agent": log_data["user_agent"],
            "completion_metadata": {"entry_verification": verification_metadata},
        }
        participant_session, created = ParticipantSession.objects.get_or_create(
            recruitment_source=source,
            external_pid=external_pid,
            defaults=session_defaults,
        )
        if not created:
            participant_session.user = participant_session.user or user
            participant_session.enrollment = participant_session.enrollment or enrollment
            participant_session.raw_query_string = log_data["raw_query_string"]
            participant_session.referer = log_data["referer"]
            participant_session.ip_address = log_data["ip_address"]
            participant_session.user_agent = log_data["user_agent"]
            metadata = participant_session.completion_metadata or {}
            metadata["last_entry_verification"] = verification_metadata
            participant_session.completion_metadata = metadata

        if not participant_session.condition:
            participant_session.condition = assign_condition(source, external_pid, participant_session)
        participant_session.save()

        entry_log = RecruitmentEntryLog.objects.create(
            **log_data,
            participant_session=participant_session,
            accepted=True,
        )

    if participant_session.status == ParticipantSession.STATUS_COMPLETED:
        return redirect("recruitment:already_completed", session_uuid=participant_session.uuid)

    request.session["participant_session_uuid"] = str(participant_session.uuid)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("recruitment:consent", session_uuid=participant_session.uuid)


@login_required
@require_http_methods(["GET", "POST"])
def consent(request, session_uuid):
    participant_session = get_object_or_404(
        ParticipantSession.objects.select_related("recruitment_source"),
        uuid=session_uuid,
    )
    if request.user != participant_session.user and not request.user.is_staff:
        raise PermissionDenied("You cannot open another participant session.")
    if request.method == "POST":
        if participant_session.status == ParticipantSession.STATUS_ENTERED:
            participant_session.status = ParticipantSession.STATUS_CONSENTED
            participant_session.save(update_fields=["status", "updated_at"])
        return redirect("courses:course_detail", instance_id=participant_session.recruitment_source.course_instance_id)
    return render(request, "recruitment/consent.html", {"participant_session": participant_session})


@login_required
def already_completed(request, session_uuid):
    participant_session = get_object_or_404(ParticipantSession, uuid=session_uuid)
    return render(request, "recruitment/already_completed.html", {"participant_session": participant_session})


@login_required
def thank_you(request, session_uuid):
    participant_session = get_object_or_404(ParticipantSession, uuid=session_uuid)
    return render(request, "recruitment/thank_you.html", {"participant_session": participant_session})


@login_required
def complete(request, session_uuid):
    participant_session = get_object_or_404(
        ParticipantSession.objects.select_related("recruitment_source", "enrollment", "enrollment__course_progress"),
        uuid=session_uuid,
    )
    if request.user != participant_session.user and not request.user.is_staff:
        raise PermissionDenied("You cannot complete another participant session.")

    outcome = request.GET.get("outcome") or _determine_outcome(participant_session)
    valid_outcomes = {
        ParticipantSession.STATUS_COMPLETED,
        ParticipantSession.STATUS_SCREENED_OUT,
        ParticipantSession.STATUS_ATTENTION_FAILED,
    }
    if outcome not in valid_outcomes:
        return HttpResponseBadRequest("Invalid completion outcome.")

    source = participant_session.recruitment_source
    if source.platform == RecruitmentSource.PLATFORM_PROLIFIC:
        code = _prolific_code_for_outcome(source, outcome)
        participant_session.mark_complete(outcome, code=code)
        participant_session.save(update_fields=["status", "completed_at", "completion_code_used", "completion_metadata", "updated_at"])
        if code:
            return redirect(completion_url(code))
        messages.warning(request, "No Prolific completion code is configured for this outcome.")
        return redirect("recruitment:thank_you", session_uuid=participant_session.uuid)

    if source.platform == RecruitmentSource.PLATFORM_SONA:
        if source.sona_grant_server_side and outcome == ParticipantSession.STATUS_COMPLETED:
            try:
                metadata = grant_credit_server_side(source, participant_session.external_pid)
                participant_session.mark_complete(outcome, metadata={"sona_credit": metadata})
                participant_session.save(update_fields=["status", "completed_at", "completion_metadata", "updated_at"])
                return redirect("recruitment:thank_you", session_uuid=participant_session.uuid)
            except SonaCreditError as exc:
                participant_session.mark_complete(outcome, metadata={"sona_credit_error": str(exc)})
                participant_session.save(update_fields=["status", "completed_at", "completion_metadata", "updated_at"])
                messages.error(request, "Your study response was recorded, but SONA credit needs manual review.")
                return redirect("recruitment:thank_you", session_uuid=participant_session.uuid)

        participant_session.mark_complete(outcome)
        participant_session.save(update_fields=["status", "completed_at", "completion_metadata", "updated_at"])
        if outcome == ParticipantSession.STATUS_COMPLETED:
            return redirect(client_credit_url(source, participant_session.external_pid))
        return redirect("recruitment:thank_you", session_uuid=participant_session.uuid)

    return redirect("recruitment:thank_you", session_uuid=participant_session.uuid)


def _determine_outcome(participant_session: ParticipantSession) -> str:
    try:
        progress = participant_session.enrollment.course_progress
    except Exception:
        progress = None
    if progress and progress.is_complete:
        return ParticipantSession.STATUS_COMPLETED
    return participant_session.status if participant_session.is_finished else ParticipantSession.STATUS_COMPLETED


def _prolific_code_for_outcome(source: RecruitmentSource, outcome: str) -> str:
    if outcome == ParticipantSession.STATUS_SCREENED_OUT:
        return source.prolific_completion_code_screened_out or source.prolific_completion_code_complete
    if outcome == ParticipantSession.STATUS_ATTENTION_FAILED:
        return source.prolific_completion_code_attention_failed or source.prolific_completion_code_complete
    return source.prolific_completion_code_complete


@login_required
@require_POST
def create_source(request, course_instance_id):
    from courses.models import CourseInstance

    course_instance = get_object_or_404(CourseInstance, id=course_instance_id)
    if not course_instance.instructors.filter(id=request.user.id).exists():
        raise PermissionDenied("Only this session's instructors can configure recruitment.")

    platform = request.POST.get("platform", "").strip()
    if platform not in {RecruitmentSource.PLATFORM_PROLIFIC, RecruitmentSource.PLATFORM_SONA}:
        messages.error(request, "Choose Prolific or SONA for the recruitment source.")
        return redirect("dashboard:instructor_dashboard")

    existing_source = RecruitmentSource.objects.filter(course_instance=course_instance, platform=platform).first()

    def posted_or_existing(field_name):
        value = request.POST.get(field_name, "").strip()
        if value or not existing_source:
            return value
        return getattr(existing_source, field_name, "") or ""

    defaults = {
        "label": request.POST.get("label", "").strip() or (existing_source.label if existing_source else ""),
        "is_active": request.POST.get("is_active") == "on",
        "max_participants": _optional_int(request.POST.get("max_participants")),
        "condition_strategy": request.POST.get("condition_strategy") or RecruitmentSource.CONDITION_HASH,
        "condition_labels": request.POST.get("condition_labels", "").strip(),
        "prolific_study_id": posted_or_existing("prolific_study_id"),
        "prolific_completion_code_complete": posted_or_existing("prolific_completion_code_complete"),
        "prolific_completion_code_screened_out": posted_or_existing("prolific_completion_code_screened_out"),
        "prolific_completion_code_attention_failed": posted_or_existing("prolific_completion_code_attention_failed"),
        "prolific_use_secured_url": request.POST.get("prolific_use_secured_url") == "on",
        "sona_base_url": posted_or_existing("sona_base_url"),
        "sona_experiment_id": posted_or_existing("sona_experiment_id"),
        "sona_credit_token": posted_or_existing("sona_credit_token"),
        "sona_grant_server_side": request.POST.get("sona_grant_server_side") == "on",
    }

    source, created = RecruitmentSource.objects.update_or_create(
        course_instance=course_instance,
        platform=platform,
        defaults=defaults,
    )
    course = course_instance.course
    if course and not course.is_locked_for_research:
        course.is_locked_for_research = True
        course.save(update_fields=["is_locked_for_research"])
    messages.success(request, f"{'Created' if created else 'Updated'} {source.get_platform_display()} recruitment for {course_instance}.")
    return redirect("dashboard:instructor_dashboard")


def _optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@login_required
def export_sessions(request, source_id):
    source = get_object_or_404(RecruitmentSource.objects.select_related("course_instance"), id=source_id)
    if not source.course_instance.instructors.filter(id=request.user.id).exists() and not request.user.is_staff:
        raise PermissionDenied("Only this session's instructors can export recruitment data.")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="recruitment-source-{source.id}-participants.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "uuid",
        "platform",
        "external_pid",
        "external_study_id",
        "external_session_id",
        "condition",
        "status",
        "entered_at",
        "completed_at",
        "completion_code_used",
        "enrollment_id",
        "user_id",
    ])
    for session in source.participant_sessions.select_related("user", "enrollment").order_by("entered_at"):
        writer.writerow([
            session.uuid,
            source.platform,
            session.external_pid,
            session.external_study_id,
            session.external_session_id,
            session.condition,
            session.status,
            session.entered_at.isoformat() if session.entered_at else "",
            session.completed_at.isoformat() if session.completed_at else "",
            session.completion_code_used,
            session.enrollment_id or "",
            session.user_id or "",
        ])
    return response

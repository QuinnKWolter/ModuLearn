from __future__ import annotations

import hashlib

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from recruitment.models import ParticipantSession, RecruitmentAssignmentSlot, RecruitmentSource


def assign_condition(source: RecruitmentSource, external_pid: str, participant_session: ParticipantSession | None = None) -> str:
    conditions = source.conditions
    if not conditions:
        return "default"

    if source.condition_strategy == RecruitmentSource.CONDITION_SCHEDULE:
        condition = _assign_from_schedule(source, participant_session)
        if condition:
            return condition

    if source.condition_strategy == RecruitmentSource.CONDITION_BALANCED:
        return _assign_balanced(source, conditions)

    return _assign_hash(external_pid, conditions)


def _assign_hash(external_pid: str, conditions: list[str]) -> str:
    digest = hashlib.sha256((external_pid or "").encode("utf-8")).hexdigest()
    index = int(digest[:12], 16) % len(conditions)
    return conditions[index]


def _assign_balanced(source: RecruitmentSource, conditions: list[str]) -> str:
    counts = {condition: 0 for condition in conditions}
    rows = (
        ParticipantSession.objects.filter(recruitment_source=source, condition__in=conditions)
        .values("condition")
        .annotate(total=Count("id"))
    )
    for row in rows:
        counts[row["condition"]] = row["total"]
    return min(conditions, key=lambda condition: (counts.get(condition, 0), conditions.index(condition)))


def _assign_from_schedule(source: RecruitmentSource, participant_session: ParticipantSession | None) -> str:
    with transaction.atomic():
        slot = (
            RecruitmentAssignmentSlot.objects.select_for_update()
            .filter(source=source, claimed_by__isnull=True)
            .order_by("slot_index")
            .first()
        )
        if not slot:
            return ""
        if participant_session and participant_session.pk:
            slot.claimed_by = participant_session
            slot.claimed_at = timezone.now()
            slot.save(update_fields=["claimed_by", "claimed_at"])
        return slot.condition

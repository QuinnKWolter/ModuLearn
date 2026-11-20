"""Server-owned study cursor. Ordinary courses retain their existing navigation.

Branch rules select remediation; each visit returns to its triggering activity.
The cursor, deadlines and transition audit survive refreshes and browser closes.
"""
from datetime import timedelta
from copy import deepcopy

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from courses.models import Module, ModuleBranchRule, ModuleProgressEvent
from recruitment.models import ParticipantSession
from modulearn.learning.services.course_plugins import is_course_plugin_enabled


def guided_session(enrollment):
    if not enrollment:
        return None
    if not enrollment.course_instance.course.is_locked_for_research:
        return None
    return ParticipantSession.objects.select_related('recruitment_source__study').filter(
        enrollment=enrollment, recruitment_source__study__guided_flow=True,
    ).exclude(status__in=['rejected', 'abandoned']).first()


def condition_visible(item, condition):
    rule = item.unlock_rule or {}
    checks = [str(entry.get('target_id', '')) == condition
        for entry in rule.get('conditions', []) if entry.get('type') == 'condition_equals']
    return not checks or (any(checks) if rule.get('mode') == 'any' else all(checks))


def _modules(session):
    course = session.recruitment_source.resolved_course_instance.course
    modules = list(Module.objects.filter(unit__course=course, unit__is_visible=True,
        is_visible=True, is_recommendation_only=False).select_related('unit').order_by(
        'unit__order', 'unit_id', 'order', 'id'))
    return [m for m in modules if condition_visible(m, session.condition) and condition_visible(m.unit, session.condition)]


def _main_modules(session, modules):
    course = session.recruitment_source.resolved_course_instance.course
    # Disabling a rule must not accidentally insert its remediation into the main sequence.
    targets = set(ModuleBranchRule.objects.filter(course=course,
        condition_type__in=['failure', 'score_lt']).values_list('target_module_id', flat=True))
    return [m for m in modules if m.id not in targets]


def _transition(session, state, target, reason, event=None):
    before = state.get('current')
    started = parse_datetime(state.get('visit_started_at', ''))
    elapsed = max(0, (timezone.now() - started).total_seconds()) if started else None
    state.pop('pending_transition', None)
    state.pop('visit_started_at', None)
    state['current'] = target.id if target else None
    state['finished'] = target is None
    # Separate audit rows, not an ever-growing JSON history on the session.
    if before:
        from courses.models import ModuleProgress
        progress = ModuleProgress.objects.filter(enrollment=session.enrollment, module_id=before).first()
        if progress:
            ModuleProgressEvent.objects.create(module_progress=progress, user=session.user,
                module_id=before, course_instance=session.enrollment.course_instance,
                study_participant_session=session, study_condition=session.condition,
                event_type='study_transition', source='study_flow',
                progress=progress.progress, score=progress.score, success=progress.success,
                payload={'from': before, 'to': state['current'], 'reason': reason,
                         'elapsed_seconds': elapsed, 'visit_started_at': started.isoformat() if started else None,
                         'trigger_event_id': event.id if event else None})


def _route(session, state, target, reason, event, return_to=None):
    """Keep access to the current activity while its feedback is being reviewed."""
    if session.recruitment_source.study.participant_paced and event.module.module_type not in Module.FORM_LIKE_TYPES:
        state['pending_transition'] = {'from': event.module_id, 'to': target.id if target else None,
            'reason': reason, 'event_id': event.pk, 'return_to': return_to}
    else:
        state.pop('return_to', None)
        if return_to:
            state['return_to'] = return_to
        _transition(session, state, target, reason, event)


def can_acknowledge(activity):
    if not activity:
        return False
    return activity.module_type in {Module.MODULE_TYPE_FILE, Module.MODULE_TYPE_EXTERNAL_LINK} or (
        activity.module_type in {Module.MODULE_TYPE_SPLICE_SMART_CONTENT, Module.MODULE_TYPE_IMPORTED} and
        (activity.content_data or {}).get('study_allow_next') is True)


@transaction.atomic
def advance_pending(session, activity_id):
    session = ParticipantSession.objects.select_for_update().get(pk=session.pk)
    current, _ = current_activity(session)
    session.refresh_from_db(fields=['flow_state'])
    state = deepcopy(session.flow_state)
    pending = state.get('pending_transition')
    if not current or current.pk != activity_id or not pending or pending['from'] != activity_id:
        return False
    modules = {m.pk: m for m in _modules(session)}
    if pending['to'] is not None and pending['to'] not in modules:
        return False
    state.pop('return_to', None)
    if pending.get('return_to'):
        state['return_to'] = pending['return_to']
    event = ModuleProgressEvent.objects.filter(pk=pending['event_id'], study_participant_session=session).first()
    _transition(session, state, modules.get(pending['to']), pending['reason'], event)
    session.flow_state = state
    session.save(update_fields=['flow_state'])
    return True


def _next(session, modules, current):
    main = _main_modules(session, modules)
    ids = [m.id for m in main]
    if not current or current.id not in ids:
        return None
    index = ids.index(current.id) + 1
    return main[index] if index < len(main) else None


@transaction.atomic
def current_activity(session, *, start_timer=False):
    session = ParticipantSession.objects.select_for_update(of=('self',)).select_related(
        'recruitment_source__study', 'enrollment__course_instance').get(pk=session.pk)
    state = deepcopy(session.flow_state or {})
    modules = _modules(session)
    by_id = {m.id: m for m in modules}
    if 'current' not in state:
        main = _main_modules(session, modules)
        state['current'] = main[0].id if main else None
        state['finished'] = not main
    current = by_id.get(state.get('current'))
    return_module = by_id.get(state.get('return_to'))
    active_units = {m.unit_id for m in (current, return_module) if m}
    deadlines = state.setdefault('deadlines', {})
    expired_units = set(state.get('expired_units', []))
    for unit_id, value in deadlines.items():
        deadline = parse_datetime(value)
        if int(unit_id) in active_units and deadline and timezone.now() >= deadline:
            expired_units.add(int(unit_id))
    # During remediation the original section's timer continues running.
    if current and (current.unit_id in expired_units or (return_module and return_module.unit_id in expired_units)):
        origin = return_module or current
        main = _main_modules(session, modules)
        later = [m for m in main if (m.unit.order, m.unit_id) > (origin.unit.order, origin.unit_id)
                 and m.unit_id not in expired_units]
        state.pop('return_to', None)
        _transition(session, state, later[0] if later else None, 'section_timeout')
        current = by_id.get(state.get('current'))
    state['expired_units'] = sorted(expired_units)
    if start_timer and current:
        state.setdefault('visit_started_at', timezone.now().isoformat())
    if start_timer and current and current.unit.time_limit_seconds:
        deadlines.setdefault(str(current.unit_id), (timezone.now() + timedelta(
            seconds=current.unit.time_limit_seconds)).isoformat())
    if session.flow_state != state:
        session.flow_state = state
        session.save(update_fields=['flow_state'])
    return current, state


@transaction.atomic
def handle_study_event(event):
    if event.event_type not in {'attempt', 'outcome', 'completion', 'progress'}:
        return
    session = guided_session(event.module_progress.enrollment)
    if not session or session.is_finished:
        return
    current, _ = current_activity(session)
    if not current or current.id != event.module_id:
        return  # Late callbacks from another activity cannot move the study cursor.
    session = ParticipantSession.objects.select_for_update(of=('self',)).select_related(
        'recruitment_source__study', 'enrollment__course_instance').get(pk=session.pk)
    state = dict(session.flow_state)
    if state.get('pending_transition') and event.event_type not in {'attempt', 'outcome'}:
        return  # Paired completion callbacks must not overwrite the submission's branch.
    if event.event_type == 'progress' and not (state.get('return_to') and event.progress >= 1):
        return
    if event.id <= state.get('last_event_id', 0):
        return
    if event.event_type not in {'completion', 'progress'} and event.score is None:
        return
    state['last_event_id'] = event.id
    modules = _modules(session)
    by_id = {m.id: m for m in modules}
    if state.get('return_to'):
        # A practice submission, correct or incorrect, ends this remediation visit.
        origin = by_id.get(state['return_to'])
        target = origin if session.recruitment_source.study.retry_after_remediation else _next(session, modules, origin)
        _route(session, state, target, 'return_from_remediation', event)
        # A completion emitted alongside this attempt belongs to the same visit.
    elif event.success or event.event_type == 'completion' or current.completion_rule == Module.COMPLETION_SUBMISSION:
        target = _next(session, modules, current)
        from modulearn.learning.services.adaptive_branching import _rule_matches
        course = session.recruitment_source.resolved_course_instance.course
        if is_course_plugin_enabled(course, 'adaptive_branching'):
            rule = next((r for r in ModuleBranchRule.objects.filter(course=course, source_module=current,
                active=True).order_by('priority', 'id') if r.target_module_id in by_id
                and r.target_module_id != current.id
                and _rule_matches(r, event, event.module_progress, session.enrollment)), None)
            if rule:
                target = by_id[rule.target_module_id]
        _route(session, state, target, 'correct_or_complete', event)
    else:
        state.pop('pending_transition', None)
        from modulearn.learning.services.adaptive_branching import _rule_matches
        course = session.recruitment_source.resolved_course_instance.course
        if is_course_plugin_enabled(course, 'adaptive_branching'):
            rules = ModuleBranchRule.objects.filter(course=course, source_module=current,
                active=True).order_by('priority', 'id')
            rule = next((r for r in rules if r.target_module_id in by_id and r.target_module_id != current.id
                and _rule_matches(r, event, event.module_progress, session.enrollment)), None)
            if rule:
                _route(session, state, by_id[rule.target_module_id], 'incorrect_remediation', event, return_to=current.id)
    session.flow_state = state
    session.save(update_fields=['flow_state'])


def allows_activity(enrollment, module):
    session = guided_session(enrollment)
    if not session:
        return None
    current, _ = current_activity(session)
    return bool(not session.is_finished and current and current.id == module.id)

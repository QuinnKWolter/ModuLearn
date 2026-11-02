"""Researcher-only study setup and isolated participant rehearsal."""
import csv
import uuid

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_POST

from courses.models import Enrollment, Module, ModuleBranchRule, ModuleProgressEvent
from recruitment.models import Study, StudyCondition, ParticipantSession
from recruitment.services.studies import create_study_for_instructor, export_study_to_json, delete_study_completely


def managed_study(user, pk):
    study = get_object_or_404(Study.objects.select_related('course_instance__course'), pk=pk)
    if not (user.is_staff or study.instructors.filter(pk=user.pk).exists()):
        raise PermissionDenied('Only this study’s researchers can manage it.')
    return study


def editable(study):
    if study.recruitment_sources.filter(participant_sessions__isnull=False).exists():
        raise ValueError('This study already has participant data. Duplicate it to revise the protocol safely.')


@login_required
def studio(request, study_id):
    study = managed_study(request.user, study_id)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Lock the study while applying a complete edit; invalid values roll back together.
                Study.objects.select_for_update().get(pk=study.pk)
                editable(study)
                action = request.POST.get('action', 'save')
                if action == 'copy_rules':
                    source, target = request.POST.get('from_condition'), request.POST.get('to_condition')
                    labels = set(study.conditions.values_list('label', flat=True))
                    if source not in labels or target not in labels or source == target:
                        raise ValueError('Choose two different conditions.')
                    rules = ModuleBranchRule.objects.filter(course=study.course_instance.course,
                        required_study_condition=source)
                    for rule in rules:
                        ModuleBranchRule.objects.get_or_create(course=rule.course,
                            source_module=rule.source_module, target_module=rule.target_module,
                            condition_type=rule.condition_type, required_study_condition=target,
                            defaults={'threshold': rule.threshold, 'priority': rule.priority, 'active': rule.active})
                elif action == 'delete_unit':
                    unit = get_object_or_404(study.course_instance.course.units, pk=request.POST.get('unit_id'))
                    if request.POST.get('confirm_title') != unit.title:
                        raise ValueError('Type the unit title to confirm deletion.')
                    ids = set(unit.modules.values_list('id', flat=True))
                    others = list(study.course_instance.course.units.exclude(pk=unit.pk)) + list(
                        Module.objects.filter(unit__course=study.course_instance.course).exclude(unit=unit))
                    for item in others:
                        for condition in (item.unlock_rule or {}).get('conditions', []):
                            target = str(condition.get('target_id', ''))
                            if target in {str(i) for i in ids} and 'module' in condition.get('type', ''):
                                raise ValueError('Another activity depends on this unit. Remove that unlock rule first.')
                            if target == str(unit.pk) and condition.get('type') in {'unit_completed', 'unit_accessed'}:
                                raise ValueError('Another unit depends on this unit. Remove that unlock rule first.')
                    unit.delete()  # Branch rules to/from deleted activities cascade with the unit.
                else:
                    study.title = request.POST.get('title', '').strip()
                    if not study.title or len(study.title) > 255:
                        raise ValueError('Enter a study title of up to 255 characters.')
                    study.description = request.POST.get('description', '').strip()
                    study.version_label = request.POST.get('version_label', '').strip()[:64]
                    study.notes = request.POST.get('notes', '').strip()
                    study.guided_flow = request.POST.get('guided_flow') == 'on'
                    study.save()
                    strategy = request.POST.get('assignment', '')
                    from recruitment.models import RecruitmentSource
                    if strategy:
                        if strategy not in dict(RecruitmentSource.CONDITION_STRATEGY_CHOICES):
                            raise ValueError('Choose a valid assignment strategy.')
                        study.recruitment_sources.update(condition_strategy=strategy)
                    labels = set()
                    for condition in study.conditions.all():
                        label = request.POST.get(f'condition_{condition.pk}_label', condition.label).strip()
                        if not label or len(label) > 32 or not all(c.isalnum() or c in '_-' for c in label) or label in labels:
                            raise ValueError('Condition IDs must be unique, up to 32 letters, numbers, hyphens or underscores.')
                        labels.add(label)
                        if label != condition.label and study.conditions.exclude(pk=condition.pk).filter(label=label).exists():
                            raise ValueError('That condition ID is already in use.')
                        ModuleBranchRule.objects.filter(course=study.course_instance.course,
                            required_study_condition=condition.label).update(required_study_condition=label)
                        # Keep visibility/unlock conditions in sync when an ID is renamed.
                        for item in [*study.course_instance.course.units.all(), *Module.objects.filter(unit__course=study.course_instance.course)]:
                            rule = item.unlock_rule or {}
                            changed = False
                            for entry in rule.get('conditions', []):
                                if entry.get('type') == 'condition_equals' and entry.get('target_id') == condition.label:
                                    entry['target_id'] = label
                                    changed = True
                            if changed:
                                item.unlock_rule = rule
                                item.save(update_fields=['unlock_rule'])
                        condition.label = label
                        condition.name = request.POST.get(f'condition_{condition.pk}_name', condition.name).strip()[:120]
                        condition.description = request.POST.get(f'condition_{condition.pk}_description', '').strip()
                        condition.is_active = request.POST.get(f'condition_{condition.pk}_active') == 'on'
                        condition.save()
                    new_label = request.POST.get('new_condition', '').strip()
                    if new_label:
                        if len(new_label) > 32 or not all(c.isalnum() or c in '_-' for c in new_label) or new_label in labels:
                            raise ValueError('Enter a unique condition ID using letters, numbers, hyphens or underscores.')
                        StudyCondition.objects.create(study=study, label=new_label, name=new_label.replace('_', ' ').title(), order=100)
                    if not study.conditions.filter(is_active=True).exists():
                        raise ValueError('Keep at least one condition active.')
                    for unit in study.course_instance.course.units.all():
                        seconds = int(request.POST.get(f'unit_{unit.pk}_seconds', unit.time_limit_seconds) or 0)
                        if not 0 <= seconds <= 86400:
                            raise ValueError('Section timers must be between 0 and 86400 seconds.')
                        unit.time_limit_seconds = seconds
                        unit.save(update_fields=['time_limit_seconds'])
                    for module in Module.objects.filter(unit__course=study.course_instance.course, module_type__in=Module.FORM_LIKE_TYPES):
                        data = dict(module.content_data or {})
                        data['study_shuffle_questions'] = request.POST.get(f'shuffle_{module.pk}') == 'on'
                        module.content_data = data
                        module.save(update_fields=['content_data'])
            messages.success(request, 'Study setup saved.')
            return redirect('recruitment:studio', study_id=study.pk)
        except (ValueError, TypeError) as exc:
            messages.error(request, str(exc))
            study.refresh_from_db()
    return render(request, 'recruitment/studio.html', {'study': study,
        'units': study.course_instance.course.units.prefetch_related('modules').all(),
        'conditions': study.conditions.all(),
        'preview_count': study.previews.filter(instructors=request.user).count(),
        'assignment': study.recruitment_sources.first().condition_strategy if study.recruitment_sources.exists() else 'random',
        'locked': study.recruitment_sources.filter(participant_sessions__isnull=False).exists()})


@login_required
@require_POST
def clear_previews(request, study_id):
    study = managed_study(request.user, study_id)
    with transaction.atomic():
        for clone in study.previews.filter(instructors=request.user):
            delete_study_completely(clone)
    messages.success(request, 'Previous preview runs removed. The study and its participants were not changed.')
    return redirect('recruitment:studio', study_id=study.pk)


@login_required
@require_POST
def duplicate(request, study_id):
    study = managed_study(request.user, study_id)
    clone = create_study_for_instructor(request.user, title=f'{study.title[:230]} (Copy)',
        description=study.description, version_label=study.version_label,
        template_data=export_study_to_json(study))
    # A copy must never silently award credit or accept recruitment intended for its source.
    clone.recruitment_sources.update(is_active=False, prolific_completion_code_complete='',
        prolific_completion_code_screened_out='', prolific_completion_code_attention_failed='')
    return redirect('recruitment:studio', study_id=clone.pk)


@login_required
@require_POST
def preview(request, study_id):
    study = managed_study(request.user, study_id)
    if not study.guided_flow:
        messages.error(request, 'Enable and save Guided Participant Flow before rehearsing this protocol.')
        return redirect('recruitment:studio', study_id=study.pk)
    condition = get_object_or_404(study.conditions, label=request.POST.get('condition'), is_active=True)
    with transaction.atomic():
        clone = create_study_for_instructor(request.user, title=f'Preview: {study.title[:230]}',
            description=study.description, template_data=export_study_to_json(study))
        clone.preview_of = study
        clone.guided_flow = True
        clone.save(update_fields=['preview_of', 'guided_flow'])
        clone.recruitment_sources.update(is_active=False, prolific_completion_code_complete='',
            prolific_completion_code_screened_out='', prolific_completion_code_attention_failed='')
        source = clone.recruitment_sources.first()
        user = get_user_model().objects.create_user(username=f'preview-{uuid.uuid4().hex}',
            is_student=True, is_anonymous_participant=True)
        enrollment = Enrollment.objects.create(student=user, course_instance=clone.course_instance)
        session = ParticipantSession.objects.create(user=user, enrollment=enrollment,
            recruitment_source=source, condition=condition.label, external_pid=user.username)
    return_identity = [request.user.pk, request.user.get_session_auth_hash(), study.pk, clone.pk]
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session['study_preview_return'] = return_identity
    return redirect('recruitment:resume_session', session_uuid=session.uuid)


@login_required
@require_POST
def exit_preview(request):
    identity = request.session.get('study_preview_return')
    if not identity:
        raise PermissionDenied('No researcher preview is active.')
    user = get_object_or_404(get_user_model(), pk=identity[0], is_active=True)
    if not constant_time_compare(user.get_session_auth_hash(), identity[1]):
        raise PermissionDenied('Sign in again to return to study setup.')
    clone = Study.objects.filter(pk=identity[3], preview_of_id=identity[2], instructors=user).first()
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session.pop('study_preview_return', None)
    if clone:
        delete_study_completely(clone)
    if Study.objects.filter(pk=identity[2]).exists():
        return redirect('recruitment:studio', study_id=identity[2])
    return redirect('dashboard:instructor_dashboard')


@login_required
def flow_status(request, session_uuid):
    session = get_object_or_404(ParticipantSession.objects.select_related('recruitment_source__study'),
        uuid=session_uuid, user=request.user, enrollment__isnull=False)
    if not session.recruitment_source.study or not session.recruitment_source.study.guided_flow:
        return JsonResponse({'error': 'Guided study flow is not enabled.'}, status=400)
    from recruitment.services.flow import current_activity
    activity, state = current_activity(session)
    url = reverse('courses:launch_iframe_module', args=[session.enrollment.course_instance_id, activity.pk]) if activity else reverse(
        'recruitment:complete', args=[session.uuid])
    deadlines = state.get('deadlines', {})
    active_deadlines = [value for key, value in deadlines.items() if int(key) not in state.get('expired_units', [])
        and (activity and int(key) == activity.unit_id or state.get('return_to') and Module.objects.filter(
            pk=state['return_to'], unit_id=key).exists())]
    response = JsonResponse({'url': url, 'finished': state.get('finished', False),
        'deadline': min(active_deadlines) if active_deadlines else None, 'server_time': timezone.now().isoformat(),
        'trace': list(ModuleProgressEvent.objects.filter(study_participant_session=session,
            event_type__in=['attempt', 'completion', 'study_transition', 'study_late_event']).order_by('-pk')
            .values('created_at', 'module__title', 'event_type', 'score', 'success', 'source')[:30])
            if session.recruitment_source.study.preview_of_id and request.GET.get('trace') == '1' else None})
    response['Cache-Control'] = 'no-store'
    return response


@login_required
def events_csv(request, study_id):
    study = managed_study(request.user, study_id)
    import json
    def safe(value):
        value = str(value if value is not None else '')
        return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
    rows = ModuleProgressEvent.objects.filter(study_participant_session__recruitment_source__study=study).select_related(
        'module', 'study_participant_session').order_by('created_at', 'pk')
    class Echo:
        def write(self, value):
            return value
    def generate():
        writer = csv.writer(Echo())
        yield writer.writerow(['participant', 'condition', 'activity_id', 'activity', 'event', 'timestamp', 'score', 'success', 'source', 'details'])
        for event in rows.iterator(chunk_size=500):
            yield writer.writerow([safe(x) for x in [event.study_participant_session.uuid, event.study_condition,
                event.module_id, event.module.title, event.event_type, event.created_at.isoformat(),
                event.score, event.success, event.source, json.dumps(event.payload, ensure_ascii=False)]])
    response = StreamingHttpResponse(generate(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="study-events.csv"'
    return response


@login_required
@require_POST
def input_summary(request, session_uuid):
    import json
    from courses.models import ModuleProgress
    from modulearn.learning.services.progress import log_module_progress_event
    session = get_object_or_404(ParticipantSession, uuid=session_uuid, user=request.user, enrollment__isnull=False)
    try:
        raw = request.POST.get('summary', '{}')
        if len(raw) > 64000:
            raise ValueError()
        data = json.loads(raw)
        activity_id = int(data.get('activity_id', 0))
        values = data.get('fields', {})
        if not isinstance(values, dict) or len(values) > 100:
            raise ValueError()
        progress = get_object_or_404(ModuleProgress, enrollment=session.enrollment, module_id=activity_id, user=request.user)
        if not progress.events.filter(event_type='launch').exists():
            raise PermissionDenied('This activity has not been opened.')
        payload = {'fields': {}}
        valid_names = {f'question_{pk}' for pk in progress.module.form.questions.values_list('pk', flat=True)}
        for name, counters in values.items():
            if name not in valid_names or not isinstance(counters, dict):
                raise ValueError()
            payload['fields'][name] = {key: max(0, min(1000000, int(counters.get(key, 0))))
                for key in ['keystrokes', 'paste_count', 'copy_count', 'characters']}
        payload['kind'] = 'cumulative_per_page_visit'
        payload['visit_id'] = str(data.get('visit_id', ''))[:64]
        log_module_progress_event(progress, event_type='study_input', source='study_form', payload=payload)
        return JsonResponse({'saved': True})
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Invalid input summary.'}, status=400)


@login_required
@require_POST
def continue_resource(request, session_uuid):
    session = get_object_or_404(ParticipantSession, uuid=session_uuid, user=request.user,
        enrollment__isnull=False, recruitment_source__study__guided_flow=True)
    from recruitment.services.flow import current_activity
    from courses.models import ModuleProgress
    from modulearn.learning.services.progress import apply_progress_snapshot
    activity, _ = current_activity(session)
    if not activity or activity.module_type not in {Module.MODULE_TYPE_FILE, Module.MODULE_TYPE_EXTERNAL_LINK}:
        raise PermissionDenied('This activity must report its own result.')
    progress = get_object_or_404(ModuleProgress, enrollment=session.enrollment, module=activity, user=request.user)
    if not progress.events.filter(event_type='launch').exists():
        raise PermissionDenied('Open this resource before continuing.')
    apply_progress_snapshot(progress, source='participant_acknowledgement', event_type='completion',
        progress=1, is_complete=True, success=True, payload={'acknowledged': True})
    return redirect('recruitment:resume_session', session_uuid=session.uuid)


@login_required
@require_POST
def simulate(request, session_uuid):
    """A rehearsal-only tool; never available in an actual participant study."""
    session = get_object_or_404(ParticipantSession.objects.select_related('recruitment_source__study'),
        uuid=session_uuid, user=request.user, recruitment_source__study__preview_of__isnull=False)
    identity = request.session.get('study_preview_return')
    if not identity or identity[3] != session.recruitment_source.study_id:
        raise PermissionDenied('Researcher preview required.')
    from recruitment.services.flow import current_activity
    from courses.models import ModuleProgress
    from modulearn.learning.services.progress import apply_progress_snapshot
    activity, _ = current_activity(session)
    if activity:
        progress, _ = ModuleProgress.get_or_create_progress(user=request.user, module=activity,
            course_instance=session.enrollment.course_instance)
        correct = request.POST.get('result') == 'correct'
        apply_progress_snapshot(progress, source='researcher_simulation', event_type='attempt',
            score=100 if correct else 0, progress=1 if correct else 0,
            success=correct, is_complete=correct, payload={'simulated': True})
    return redirect('recruitment:resume_session', session_uuid=session.uuid)

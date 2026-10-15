"""Restore unprocessed free-coding checks without replaying external side effects."""
import json
from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from courses.models import CourseInstance, ModuleProgress, ModuleProgressEvent
from modulearn.learning.services.progress import recompute_course_progress


class Command(BaseCommand):
    help = 'Preview (default) or repair course progress from saved Cupcake free-coding checks.'

    def add_arguments(self, parser):
        parser.add_argument('--sessions', nargs='+', type=int, required=True)
        parser.add_argument('--modules', nargs='+', type=int, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        sessions, modules = options['sessions'], options['modules']
        if set(CourseInstance.objects.filter(pk__in=sessions).values_list('pk', flat=True)) != set(sessions):
            raise CommandError('One or more session IDs do not exist.')
        report = {'mode': 'APPLY' if options['apply'] else 'PREVIEW', 'changes': [], 'skipped': []}
        repaired_enrollments = {}
        # One transaction: failed applications roll back all rows and audit events.
        with transaction.atomic() if options['apply'] else nullcontext():
            rows = ModuleProgress.objects.filter(enrollment__course_instance_id__in=sessions,
                module_id__in=modules).select_related('module', 'enrollment__course_instance', 'user').order_by('pk')
            if options['apply']:
                rows = rows.select_for_update()
            for row in rows:
                raw = list(row.events.filter(source='cupcake', event_type='provider_event',
                    payload__cupcake__activityType='free-coding',
                    payload__cupcake__eventName='answerChecked').order_by('created_at', 'id'))
                if not raw:
                    continue
                label = {'username': row.user.username, 'session': row.enrollment.course_instance_id,
                         'module': row.module_id, 'progress_id': row.pk}
                if row.module.is_recommendation_only or not row.module.allow_resubmission:
                    report['skipped'].append({**label, 'reason': 'Practice-only or single-attempt module requires separate review.'})
                    continue
                if row.user_id != row.enrollment.student_id or row.module.unit.course_id != row.enrollment.course_instance.course_id:
                    report['skipped'].append({**label, 'reason': 'Enrollment/module ownership mismatch.'})
                    continue
                attempts = list(row.events.filter(event_type='attempt').order_by('id'))
                handled = {e.payload.get('transport_id') for e in attempts if isinstance(e.payload, dict)} - {None, ''}
                # Do not guess whether an existing counter includes unidentifiable attempts.
                if row.attempts != len(attempts) or any(not isinstance(e.payload, dict) or not e.payload.get('transport_id') for e in attempts):
                    report['skipped'].append({**label, 'reason': 'Existing attempt counter/logs need manual reconciliation.'})
                    continue
                pending, seen = [], set(handled)
                invalid = False
                for event in raw:
                    payload = event.payload
                    token = payload.get('transport_id')
                    correct = payload.get('cupcake', {}).get('eventData', {}).get('isCorrect')
                    if (not isinstance(token, str) or not token or type(correct) is not bool
                            or event.user_id != row.user_id or event.module_id != row.module_id
                            or event.course_instance_id != row.enrollment.course_instance_id):
                        invalid = True
                        break
                    if token not in seen:
                        pending.append((event, correct))
                        seen.add(token)
                if invalid:
                    report['skipped'].append({**label, 'reason': 'Malformed or mismatched source event.'})
                    continue
                if not pending:
                    continue
                successes = [event for event, correct in pending if correct]
                complete = row.is_complete or bool(successes)
                score = max(row.score if row.score is not None else 0, 100 if successes else 0)
                change = {**label, 'restored_attempts': len(pending),
                    'successful_checks': len(successes), 'before': {'attempts': row.attempts,
                    'score': row.score, 'is_complete': row.is_complete},
                    'after': {'attempts': row.attempts + len(pending), 'score': score, 'is_complete': complete},
                    'source_event_ids': [event.pk for event, _ in pending]}
                report['changes'].append(change)
                if not options['apply']:
                    continue
                completed_at = row.completed_at or (successes[0].created_at if successes else None)
                # Preserve current interaction state and last_accessed. This is historical credit,
                # not a simulated student visit or a new submission to a provider.
                ModuleProgress.objects.filter(pk=row.pk).update(attempts=change['after']['attempts'],
                    score=score, progress=max(row.progress, 1 if complete else 0),
                    is_complete=complete, success=row.success or bool(successes), completed_at=completed_at)
                for event, correct in pending:
                    payload = {**event.payload, 'historical_repair': {
                        'source_event_id': event.pk, 'applied_at': timezone.now().isoformat()}}
                    restored = ModuleProgressEvent.objects.create(module_progress=row, user_id=row.user_id,
                        module_id=row.module_id, course_instance_id=row.enrollment.course_instance_id,
                        source='cupcake', event_type='attempt', score=100 if correct else 0,
                        progress=1 if correct else 0, success=correct, payload=payload,
                        study_participant_session_id=event.study_participant_session_id,
                        study_condition=event.study_condition)
                    ModuleProgressEvent.objects.filter(pk=restored.pk).update(created_at=event.created_at)
                if successes and not row.is_complete:
                    event = successes[0]
                    restored = ModuleProgressEvent.objects.create(module_progress=row, user_id=row.user_id,
                        module_id=row.module_id, course_instance_id=row.enrollment.course_instance_id,
                        source='cupcake_repair', event_type='completion', score=100, progress=1, success=True,
                        payload={'source_event_id': event.pk, 'applied_at': timezone.now().isoformat()})
                    ModuleProgressEvent.objects.filter(pk=restored.pk).update(created_at=event.created_at)
                repaired_enrollments[row.enrollment_id] = row.enrollment
            for enrollment in repaired_enrollments.values():
                # This service updates local totals only; do not use update_progress(),
                # which can send grades to an external LMS.
                recompute_course_progress(enrollment)
        report['restored_attempts'] = sum(c['restored_attempts'] for c in report['changes'])
        report['new_completions'] = sum(not c['before']['is_complete'] and c['after']['is_complete']
                                        for c in report['changes'])
        self.stdout.write(json.dumps(report, indent=2))

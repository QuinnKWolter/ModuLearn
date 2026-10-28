"""Reconcile existing accepted Cupcake attempts; never fabricate submissions or completions."""
import hashlib
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from courses.models import CourseInstance, Module, ModuleProgress, ModuleProgressEvent
from modulearn.learning.services.cupcake_tracking import free_coding_test_score


class Command(BaseCommand):
    help = 'Preview or apply partial test scores from saved, accepted free-coding attempts.'

    def add_arguments(self, parser):
        parser.add_argument('--sessions', nargs='+', type=int, required=True)
        parser.add_argument('--modules', nargs='+', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--expect-sha256')

    def handle(self, *args, **options):
        if set(CourseInstance.objects.filter(pk__in=options['sessions']).values_list('pk', flat=True)) != set(options['sessions']):
            raise CommandError('Unknown session ID.')
        valid_modules = set(Module.objects.filter(pk__in=options['modules'],
            unit__course__instances__pk__in=options['sessions']).values_list('pk', flat=True))
        if valid_modules != set(options['modules']):
            raise CommandError('Unknown activity or activity outside the selected sessions.')
        changes, skipped = [], []
        with transaction.atomic():
            rows = ModuleProgress.objects.filter(enrollment__course_instance_id__in=options['sessions'],
                module_id__in=options['modules'], module__is_recommendation_only=False,
                enrollment__is_instructor_preview=False).select_related('module', 'user', 'enrollment').order_by('pk')
            if options['apply']:
                rows = rows.select_for_update()
            rows = list(rows)
            rows_by_id = {row.pk: row for row in rows}
            for row in rows:
                label = {'student': row.user.username, 'session': row.enrollment.course_instance_id,
                         'activity': row.module.title, 'module': row.module_id, 'progress_id': row.pk}
                attempts = list(row.events.filter(event_type='attempt').order_by('created_at', 'id'))
                if not any(e.payload.get('cupcake', {}).get('activityType') == 'free-coding' for e in attempts):
                    continue
                if (row.user_id != row.enrollment.student_id or
                    row.module.unit.course_id != row.enrollment.course_instance.course_id or
                    row.attempts != len(attempts)):
                    skipped.append({**label, 'reason': 'Ownership or attempt count mismatch; review separately.'})
                    continue
                scores, event_changes, seen = [], [], set()
                for event in attempts:
                    message = event.payload.get('cupcake', {})
                    token = event.payload.get('transport_id')
                    score = free_coding_test_score(message.get('eventData'))
                    if (event.source not in {'cupcake', 'cupcake_repair'} or
                        message.get('eventName') != 'answerChecked' or message.get('activityType') != 'free-coding' or
                        not token or token in seen or score is None or
                        event.user_id != row.user_id or event.module_id != row.module_id or
                        event.course_instance_id != row.enrollment.course_instance_id):
                        break
                    seen.add(token)
                    scores.append(score)
                    if event.score != score or event.progress < score / 100:
                        event_changes.append({'event_id': event.pk,
                            'before': {'score': event.score, 'progress': event.progress},
                            'after': {'score': score, 'progress': max(event.progress, score / 100)}})
                if len(scores) != len(attempts):
                    skipped.append({**label, 'reason': 'Missing, mixed, duplicate or contradictory test evidence; no changes.'})
                    continue
                before = {'score': row.score, 'progress': row.progress}
                # Best progress is retained; score represents the latest accepted attempt.
                # Never reduce a stored score during historical reconciliation.
                after = {'score': max(row.score or 0, scores[-1]),
                         'progress': max(row.progress, max(scores) / 100)}
                if before == after and not event_changes:
                    continue
                changes.append({**label, 'before': before, 'after': after,
                    'attempts_unchanged': row.attempts, 'completion_unchanged': row.is_complete,
                    'attempt_updates': event_changes})
            digest = hashlib.sha256(json.dumps(changes, sort_keys=True).encode()).hexdigest()
            if options['apply']:
                if options['expect_sha256'] != digest:
                    raise CommandError('Plan changed or checksum missing. Run preview again and supply --expect-sha256.')
                for change in changes:
                    ModuleProgress.objects.filter(pk=change['progress_id']).update(**change['after'])
                    for event in change['attempt_updates']:
                        ModuleProgressEvent.objects.filter(pk=event['event_id']).update(**event['after'])
                    row = rows_by_id[change['progress_id']]
                    ModuleProgressEvent.objects.create(module_progress=row, user_id=row.user_id,
                        module_id=row.module_id, course_instance_id=row.enrollment.course_instance_id,
                        event_type='progress', source='cupcake_partial_backfill',
                        score=change['after']['score'], progress=change['after']['progress'],
                        success=row.success, payload={'repair': 'partial_test_scores_v1', 'plan_sha256': digest, **change})
            # No grade recalculation/passback: completed IDs and completion-based course grades are unchanged.
        self.stdout.write(json.dumps({'mode': 'APPLY' if options['apply'] else 'PREVIEW',
            'sha256': digest, 'affected_activities': len(changes), 'changes': changes, 'skipped': skipped}, indent=2))

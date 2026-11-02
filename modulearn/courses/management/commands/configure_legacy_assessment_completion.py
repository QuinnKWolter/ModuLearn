"""Opt-in conversion of the two imported CS0401 assessment units; never replace answers."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from courses.models import CourseInstance, ModuleProgress
from modulearn.learning.services.progress import recompute_course_progress, log_module_progress_event
from modulearn.learning.services.recommendation_tracking import attempt_snapshot
from modulearn.learning.services.unit_packages import export_unit


class Command(BaseCommand):
    help = 'Preview/apply submission completion and sequential prerequisites to imported CS0401 test units.'

    def add_arguments(self, parser):
        parser.add_argument('--instance-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--output')

    @transaction.atomic
    def handle(self, *args, **options):
        instance = CourseInstance.objects.select_related('course').get(pk=options['instance_id'])
        units = []
        for unit in instance.course.units.prefetch_related('modules').all():
            modules = list(unit.modules.all())
            phases = {(m.content_data or {}).get('legacy_assessment', {}).get('phase') for m in modules}
            if phases not in ({'pretest'}, {'posttest'}):
                continue
            modules.sort(key=lambda m: m.content_data['legacy_assessment']['position'])
            if [m.content_data['legacy_assessment']['position'] for m in modules] != list(range(1, 11)):
                raise CommandError(f'{unit.title}: expected ten uniquely ordered assessment questions.')
            units.append((unit, modules, next(iter(phases))))
        if len(units) != 2 or {p for _, _, p in units} != {'pretest', 'posttest'}:
            raise CommandError('Expected exactly one imported pre-test and one post-test unit. Nothing changed.')
        self.stdout.write(f'Course: {instance.course.title}. Unit content is shared by all sessions of this course.')
        affected = set()
        for unit, modules, phase in units:
            self.stdout.write(f'{unit.title}: {len(modules)} activities; completion on first submission; sequential unlocks; retries allowed.')
            previous = None
            for module in modules:
                if options['apply']:
                    module.completion_rule = 'submission'
                    module.allow_resubmission = True
                    module.is_locked = previous is not None
                    module.unlock_rule = {'mode':'all', 'conditions':[{'type':'module_completed', 'target_id':previous.pk}]} if previous else {}
                    module.save(update_fields=['completion_rule', 'allow_resubmission', 'is_locked', 'unlock_rule'])
                previous = module
                for progress in ModuleProgress.objects.filter(module=module, is_complete=False).select_related('enrollment', 'user'):
                    evidence = None
                    for event in progress.events.filter(source__in=['quizjet', 'quizpet', 'pcrs']).order_by('created_at', 'id'):
                        if attempt_snapshot(event.source, event.payload, event.score, event.success, event.event_type):
                            evidence = event
                            break
                    if evidence is None:
                        continue
                    self.stdout.write(f'  {progress.user.username}: {module.title} -> complete (submission event {evidence.pk}; score unchanged)')
                    if options['apply']:
                        progress.progress = 1
                        progress.is_complete = True
                        progress.completed_at = evidence.created_at
                        progress.save(update_fields=['progress','is_complete','completed_at'])
                        log_module_progress_event(progress, event_type='progress', source='completion_policy',
                            payload={'completion_rule':'submission','evidence_event_id':evidence.pk,'repair':True})
                        affected.add(progress.enrollment_id)
            if options['apply'] and options['output']:
                output = Path(options['output']); output.mkdir(parents=True, exist_ok=True)
                (output / f'{phase}-unit.json').write_text(json.dumps(export_unit(unit), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if options['apply']:
            from courses.models import Enrollment
            for enrollment in Enrollment.objects.filter(pk__in=affected):
                recompute_course_progress(enrollment)
        self.stdout.write('Applied.' if options['apply'] else 'Preview only; use --apply to save.')

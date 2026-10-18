"""Read-only evidence export for a catalog integration lab."""
import json
from collections import defaultdict
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone
from courses.models import CourseInstance, Module, ModuleProgress, ModuleProgressEvent


class Command(BaseCommand):
    help = 'Export saved progress and event counts for a catalog lab; never repairs or awards credit.'

    def add_arguments(self, parser):
        parser.add_argument('--instance', type=int, required=True)
        parser.add_argument('--output')

    def handle(self, *args, **options):
        try:
            instance = CourseInstance.objects.get(pk=options['instance'])
        except CourseInstance.DoesNotExist as exc:
            raise CommandError('Course session does not exist.') from exc
        modules = list(Module.objects.filter(unit__course=instance.course).order_by('unit__order', 'order', 'pk'))
        if not modules or any(not (m.content_data or {}).get('validation') for m in modules):
            raise CommandError('This command is restricted to a catalog testing course.')
        progress = list(ModuleProgress.objects.filter(enrollment__course_instance=instance)
                        .select_related('enrollment', 'user').order_by('module_id', 'user_id'))
        counts = defaultdict(dict)
        for row in ModuleProgressEvent.objects.filter(module_progress_id__in=[p.pk for p in progress]).values(
                'module_progress_id', 'event_type').annotate(total=Count('pk')):
            counts[row['module_progress_id']][row['event_type']] = row['total']
        by_module = defaultdict(list)
        for row in progress:
            by_module[row.module_id].append({
                'username': row.user.username, 'instructor_testing': row.enrollment.is_instructor_preview,
                'score': row.score, 'progress': row.progress, 'complete': row.is_complete,
                'attempts': row.attempts, 'event_counts': counts[row.pk],
            })
        report = {'generated_at': timezone.now().isoformat(), 'instance_id': instance.pk,
                  'note': 'Saved evidence only. A launch without completion does not establish a tracking failure.',
                  'modules': [{'module_id': m.pk, 'title': m.title,
                               'coverage': m.content_data['validation'], 'evidence': by_module[m.pk]} for m in modules]}
        result = json.dumps(report, indent=2, ensure_ascii=False)
        if options['output']:
            Path(options['output']).write_text(result, encoding='utf8')
            self.stdout.write(f'Evidence exported to {options["output"]}')
        else:
            self.stdout.write(result)

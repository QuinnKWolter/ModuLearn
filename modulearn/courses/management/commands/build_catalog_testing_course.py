"""Inventory every catalog combination and optionally create a separate test course."""
import csv
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment
from modulearn.learning.services.catalog_validation import coverage_groups, candidate_order, coverage_key, SUPPORTED_DELIVERIES
from modulearn.learning.services.slc_catalog import _fetch, PITT_API, normalize_item, module_catalog_fields


class Command(BaseCommand):
    help = 'Inventory live catalog coverage; --create makes a NEW isolated course (never overwrites an existing course).'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--create', action='store_true')
        parser.add_argument('--course-id', default='slc-integration-lab-20261017')
        parser.add_argument('--teacher', default='RITEL_DEMO_Teacher')
        parser.add_argument('--student', default='RITEL_DEMO_Student')

    def handle(self, *args, **options):
        if options['create'] and Course.objects.filter(pk=options['course_id']).exists():
            raise CommandError('Course already exists; refusing to replace any modules, grades or configuration. Use another --course-id.')
        output = Path(options['output'])
        output.mkdir(parents=True, exist_ok=True)
        records = json.loads(_fetch(PITT_API))
        (output / 'catalog-list.json').write_text(json.dumps(records, ensure_ascii=False), encoding='utf8')
        details, rows = {}, []
        for (provider, kind, protocol), candidates in coverage_groups(records).items():
            row = {'key': coverage_key(provider, kind, protocol), 'provider': provider, 'type': kind, 'protocol': protocol,
                   'catalog_count': len(candidates), 'status': 'not_tested', 'catalog_id': '', 'title': '', 'url': '', 'reason': ''}
            if protocol not in SUPPORTED_DELIVERIES:
                row.update(status='unsupported_protocol', reason='No supported transport contract; do not guess from a demo URL.')
            else:
                for candidate in sorted(candidates, key=candidate_order)[:5]:
                    if str(candidate.get('status', '')).startswith('broken'):
                        row.update(status='catalog_broken', catalog_id=candidate['id'], title=candidate['identity']['title'], reason=candidate['status'])
                        continue
                    try:
                        if candidate['id'] not in details:
                            details[candidate['id']] = json.loads(_fetch(PITT_API + '/' + candidate['id']))
                        item = normalize_item('pitt', details[candidate['id']], detail=True)
                        endpoint = next((d for d in item['delivery'] if d['protocol'] == protocol and d['url']), None)
                        if not endpoint:
                            continue
                        item['selected_delivery'] = endpoint
                        row.update(catalog_id=item['id'], title=item['title'], url=endpoint['url'], fields=module_catalog_fields(item))
                        break
                    except Exception as exc:
                        row['reason'] = f'{type(exc).__name__}: {exc}'
                if not row['url'] and row['status'] == 'not_tested':
                    row['status'] = 'no_usable_delivery'
            rows.append(row)
            self.stdout.write(f"{provider} / {kind} / {protocol}: {row['title'] or row['status']}")
        report = {'fetched_at': timezone.now().isoformat(), 'record_count': len(records), 'coverage': rows}
        if options['create']:
            teacher = User.objects.get(username=options['teacher'])
            student = User.objects.get(username=options['student'])
            with transaction.atomic():
                course = Course.objects.create(id=options['course_id'], title='SLC Integration Lab',
                    description='Provider, activity type and protocol validation. Experimental integrations; see the coverage report for verified and blocked cases.')
                course.instructors.add(teacher)
                instance = CourseInstance.objects.create(course=course, group_name='SLC Integration Lab — local testing')
                instance.instructors.add(teacher)
                Enrollment.objects.create(student=student, course_instance=instance)
                units = {}
                for position, row in enumerate(rows):
                    if not row['url']:
                        continue
                    if row['provider'] not in units:
                        units[row['provider']] = Unit.objects.create(course=course, title=row['provider'], order=len(units))
                    fields = dict(row['fields'])
                    fields['content_data']['validation'] = {'key': row['key'], 'catalog_type': row['type'], 'requested_protocol': row['protocol']}
                    module = Module.objects.create(unit=units[row['provider']], title=f"[{row['protocol']}] {row['title']}"[:255],
                        description=f"{row['type']} · Catalog integration test", order=position, **fields)
                    row['module_id'] = module.pk
                report.update(course_id=course.pk, instance_id=instance.pk)
        (output / 'coverage.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
        (output / 'selected-records.json').write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding='utf8')
        with (output / 'coverage.csv').open('w', newline='', encoding='utf8') as stream:
            keys = ['provider', 'type', 'protocol', 'catalog_count', 'catalog_id', 'title', 'url', 'status', 'reason', 'module_id']
            writer = csv.DictWriter(stream, fieldnames=keys, extrasaction='ignore'); writer.writeheader(); writer.writerows(rows)
        self.stdout.write(self.style.SUCCESS(f"{len(records)} activities; {len(rows)} combinations; report: {output / 'coverage.json'}"))
        if options['create']:
            self.stdout.write(f"Local test course session: {instance.pk}")

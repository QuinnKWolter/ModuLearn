"""Build reusable CS0401 assessment units without the legacy orchestration service."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment
from courses.utils import export_course_to_json
from modulearn.learning.services.unit_packages import export_unit


class Command(BaseCommand):
    help = 'Create a separate legacy assessment test course and export both reusable units. Existing courses are never overwritten.'

    def add_arguments(self, parser):
        parser.add_argument('--teacher', default='RITEL_DEMO_Teacher')
        parser.add_argument('--student', default='RITEL_DEMO_Student')
        parser.add_argument('--course-id', default='cs0401-assessment-lab')
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        teacher = User.objects.filter(username=options['teacher'], is_instructor=True).first()
        student = User.objects.filter(username=options['student']).first()
        if not teacher or not student:
            raise CommandError('Both demo accounts must already exist. This command does not change passwords or roles.')
        if Course.objects.filter(pk=options['course_id']).exists():
            raise CommandError('Course already exists. Use a new --course-id; existing activities and records are preserved.')
        manifest = json.loads((Path(__file__).resolve().parents[2] / 'fixtures/legacy_cs0401/assessments.json').read_text(encoding='utf-8'))
        with transaction.atomic():
            course = Course.objects.create(id=options['course_id'], title='Java Pre-Test & Post-Test Lab',
                description='CS0401 assessments: ten questions per unit, with individual attempt and answer history. Questions 1–5 are tracing; 6–10 are code writing. The supplied archive contains no surveys.')
            course.instructors.add(teacher)
            instance = CourseInstance.objects.create(course=course, group_name='CS0401 Assessment Lab')
            instance.instructors.add(teacher)
            Enrollment.objects.create(student=student, course_instance=instance)
            for index, source in enumerate(manifest['units'],1):
                unit = Unit.objects.create(course=course, title=source['title'], order=index*10, description=source['instructions'])
                previous = None
                for item in source['questions']:
                    kind = 'Tracing' if item['provider']=='quizjet' else 'Code Writing'
                    topic = ['Decisions','While Loops','For Loops','Arrays','Two-dimensional Arrays','Boolean Expressions','Conditionals','Arrays','Nested Loops','Methods'][item['position']-1]
                    module = Module.objects.create(unit=unit, title=f"{item['position']:02d} · {topic}", order=item['position']*10,
                        module_type='splice_smart_content', content_url=item['url'], allow_resubmission=True,
                        completion_rule=Module.COMPLETION_SUBMISSION, is_locked=previous is not None,
                        unlock_rule={'mode': 'all', 'conditions': [{'type': 'module_completed', 'target_id': previous.pk}]} if previous else {},
                        provider_id=item['provider'], platform_name=kind, author='Roya Hosseini / PAWS Lab', supported_protocols=['html'],
                        description=f"{kind} · {source['title']}",
                        content_data={'provider_id':item['provider'], 'resource_id':item['provider'],
                            'display_type_label':kind, 'supported_protocols':['html'],
                            'legacy_assessment':{'phase':source['phase'],'item_id':item['id'],'position':item['position'],
                                'source_sha256':source['source_sha256']}})
                    previous = module
        output=Path(options['output']);output.mkdir(parents=True,exist_ok=True)
        for unit in course.units.order_by('order'):
            name='pretest' if unit.order==10 else 'posttest'
            (output/(name+'-unit.json')).write_text(json.dumps(export_unit(unit),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        (output/'course.json').write_text(json.dumps(export_course_to_json(course),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Session {instance.pk}: /courses/instance/{instance.pk}/'))
        self.stdout.write(f'Unit packages exported to {output}')

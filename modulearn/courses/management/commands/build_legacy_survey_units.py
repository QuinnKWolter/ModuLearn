"""Install portable native copies of the CS0401 Qualtrics questionnaires."""
import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from courses.models import CourseInstance, Unit, Module, ModuleForm, ModuleFormQuestion
from courses.utils import export_course_to_json
from modulearn.learning.services.unit_packages import export_unit

SOURCES = Path(__file__).resolve().parents[2] / 'fixtures/legacy_cs0401/surveys'


class Command(BaseCommand):
    help = 'Add pre/post survey units to an existing course session and export them, including the consent attachment.'

    def add_arguments(self, parser):
        parser.add_argument('--instance-id', required=True, type=int)
        parser.add_argument('--output', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        instance = CourseInstance.objects.get(pk=options['instance_id'])
        course = instance.course
        if Module.objects.filter(unit__course=course, content_data__survey__version=1).exists():
            raise CommandError('Survey activities already exist. Existing responses and content will not be overwritten.')
        output = Path(options['output'])
        output.mkdir(parents=True, exist_ok=True)
        for phase, order in [('pre', 5), ('post', 30)]:
            schema = json.loads((SOURCES / f'{phase}-survey.json').read_text(encoding='utf-8'))
            unit = Unit.objects.create(course=course, title=f'{phase.title()}-Survey', order=order,
                description='Programming background, confidence and interest questionnaire.' if phase == 'pre' else 'Programming interest and confidence questionnaire.')
            module = Module.objects.create(unit=unit, title=unit.title, order=10, module_type='form',
                is_graded=False, allow_resubmission=False, content_data={'survey': schema})
            form = ModuleForm.objects.create(module=module, allow_resubmission=False)
            position = 0
            for page in schema['pages']:
                for row in page['rows']:
                    position += 1
                    row['question_order'] = position
                    ModuleFormQuestion.objects.create(form=form, order=position, prompt=row['prompt'],
                        question_type='multiple_choice' if row['multiple'] else 'single_choice',
                        required=page['required'], options=[o['label'] or str(i) for i,o in enumerate(row['options'],1)],
                        help_text=f"{page['tag']} · {row['key']}")
            if phase == 'pre':
                module.content_file.save('ConsentVolunteer2024.pdf', ContentFile((SOURCES / 'ConsentVolunteer2024.pdf').read_bytes()), save=False)
            module.save()
            (output / f'{phase}-survey-unit.json').write_text(json.dumps(export_unit(unit), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            self.stdout.write(f'{unit.title}: activity {module.pk}, {position} response fields')
        (output / 'course.json').write_text(json.dumps(export_course_to_json(course), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Session {instance.pk}: /courses/instance/{instance.pk}/'))

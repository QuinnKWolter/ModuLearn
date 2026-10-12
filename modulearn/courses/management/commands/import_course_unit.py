import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from modulearn.learning.services.unit_import import import_unit_package


class Command(BaseCommand):
    help = 'Validate and append one verified unit package. Dry-run unless --apply is supplied.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--course-id', required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--expect-sha256')

    def handle(self, *args, **options):
        try:
            with Path(options['file']).open('rb') as file:
                raw = file.read(10 * 1024 * 1024 + 1)
            report = import_unit_package(options['course_id'], raw, apply=options['apply'], expected_sha256=options['expect_sha256'])
        except (ValueError, OSError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, indent=2))

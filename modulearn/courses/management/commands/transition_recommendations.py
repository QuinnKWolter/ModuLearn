import json
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from modulearn.learning.services.recommendation_rollout import transition_recommendations


class Command(BaseCommand):
    help = 'Dry-run an audited transition of activated recommendations in one session. No writes without --apply.'

    def add_arguments(self, parser):
        parser.add_argument('--course-id', required=True)
        parser.add_argument('--instance-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--expect-plan')

    def handle(self, *args, **options):
        try:
            report = transition_recommendations(options['course_id'], course_instance_id=options['instance_id'], apply=options['apply'], expected_plan=options['expect_plan'])
        except (ValueError, ObjectDoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, indent=2))

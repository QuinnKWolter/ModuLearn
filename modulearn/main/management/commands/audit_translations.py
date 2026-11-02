from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.translation_audit import build_inventory, serialize_inventory


class Command(BaseCommand):
    help = 'Check locale parity, interpolation, and source coverage; optionally refresh the page/message inventory.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--write', action='store_true', help='Refresh docs/translation-progress.json.')

    def handle(self, *args, **options):
        report = build_inventory(settings.BASE_DIR, [code for code, _ in settings.LANGUAGES])
        if options['write']:
            path = Path(settings.BASE_DIR) / 'docs' / 'translation-progress.json'
            path.write_text(serialize_inventory(report), encoding='utf-8')
            self.stdout.write(str(path))
        self.stdout.write(f"{len(report['pages'])} source files; " + ', '.join(f"{language}: {stats['messages']} messages" for language, stats in report['languages'].items()))
        self.stdout.write(f"Unmarked template fragments to review: {len(report['unmarked_template_text_for_review'])}")
        if report['errors']:
            raise CommandError(serialize_inventory(report['errors']))
        self.stdout.write(self.style.SUCCESS('Catalog keys and placeholders agree in every supported language.'))

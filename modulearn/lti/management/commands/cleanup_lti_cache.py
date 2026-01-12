"""
Management command to clean up expired LTI launch cache entries.

Run manually:
    python manage.py cleanup_lti_cache

Or schedule as a cron job for periodic cleanup:
    0 * * * * cd /path/to/modulearn && python manage.py cleanup_lti_cache
"""
from django.core.management.base import BaseCommand
from lti.models import LTILaunchCache


class Command(BaseCommand):
    help = 'Clean up expired LTI launch cache entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show count of entries that would be deleted without deleting them',
        )

    def handle(self, *args, **options):
        from django.utils import timezone
        
        if options['dry_run']:
            count = LTILaunchCache.objects.filter(
                expires_at__lt=timezone.now()
            ).count()
            self.stdout.write(f"Would delete {count} expired cache entries.")
        else:
            count = LTILaunchCache.cleanup_expired()
            self.stdout.write(
                self.style.SUCCESS(f"Successfully cleaned up {count} expired cache entries.")
            )


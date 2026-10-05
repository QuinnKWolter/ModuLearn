"""Read-only upstream/cache diagnostics from the actual application environment."""
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from modulearn.learning.services.slc_catalog import _load_list, SOURCES
import time
import uuid


class Command(BaseCommand):
    help = 'Check verified HTTPS catalog access and cache round trips (does not change courses).'

    def handle(self, *args, **options):
        failures = []
        for source, label in SOURCES.items():
            start = time.monotonic()
            try:
                records = _load_list(source)
                self.stdout.write(f'{label}: fetched {len(records)} records in {time.monotonic() - start:.1f}s; TLS verified')
            except Exception as exc:
                failures.append(source)
                self.stderr.write(f'{label}: upstream {type(exc).__name__}: {exc}')
                continue
            key = f'slc-catalog:diagnostic:{uuid.uuid4().hex}'
            try:
                cache.set(key, {'data': records, 'at': time.time()}, 60)
                saved = cache.get(key)
                if not saved or len(saved.get('data', [])) != len(records):
                    raise ValueError('Catalog-sized cache round trip failed')
                self.stdout.write(f'{label}: cache round trip passed')
            except Exception as exc:
                failures.append(source)
                self.stderr.write(f'{label}: cache {type(exc).__name__}: {exc}')
            finally:
                try:
                    cache.delete(key)
                except Exception:
                    pass
        if failures:
            raise CommandError('Catalog diagnostics failed; see the upstream/cache errors above.')

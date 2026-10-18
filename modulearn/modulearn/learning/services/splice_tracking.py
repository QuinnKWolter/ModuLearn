"""Retain provider interaction logs without treating them as scored attempts."""
import json
from django.db import transaction
from .progress import log_module_progress_event


def record_splice_event(progress, envelope):
    if not isinstance(envelope, dict) or len(json.dumps(envelope, allow_nan=False)) > 250000:
        raise ValueError('Invalid or oversized activity event.')
    identity, message = envelope.get('event_id'), envelope.get('message')
    if not isinstance(identity, str) or not 1 <= len(identity) <= 100:
        raise ValueError('An event ID is required.')
    if not isinstance(message, dict) or message.get('subject') != 'SPLICE.sendEvent':
        raise ValueError('Expected a SPLICE interaction event.')
    from .annotated_tracking import annotation_metadata, apply_annotation_event
    metadata = annotation_metadata(progress.module)
    with transaction.atomic():
        locked = type(progress).objects.select_for_update().get(pk=progress.pk)
        if getattr(locked, 'retired_at', None):
            raise ValueError('This recommendation has been retired.')
        if locked.events.filter(source='splice', payload__transport_id=identity).exists():
            return
        log_module_progress_event(locked, event_type='provider_event', source='splice',
            payload={'transport_id':identity, 'splice':message})
        apply_annotation_event(locked, message, metadata)

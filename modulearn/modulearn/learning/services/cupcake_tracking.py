"""Cupcake native telemetry: unknown events are logged, never guessed as grades."""
import json
import math
import re
from django.core.exceptions import PermissionDenied
from django.db import transaction
from courses.models import RecommendationProgress, ModuleProgressEvent
from .progress import apply_progress_snapshot, log_module_progress_event, module_accepts_scored_attempt


def percentage(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('Expected a finite percentage between 0 and 100.')
    return float(value)


@transaction.atomic
def record_cupcake_event(progress, envelope):
    if not isinstance(envelope, dict) or len(json.dumps(envelope, allow_nan=False)) > 250000:
        raise ValueError('Invalid or oversized activity event.')
    message = envelope.get('message')
    identity = envelope.get('event_id', '')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', identity):
        raise ValueError('An event ID is required.')
    if not isinstance(message, dict) or message.get('type') != 'cupcake:log':
        raise ValueError('Expected a Cupcake log event.')
    name, kind, data = message.get('eventName'), message.get('activityType'), message.get('eventData')
    if not isinstance(name, str) or not 1 <= len(name) <= 100 or not isinstance(kind, str) or len(kind) > 100 or not isinstance(data, dict):
        raise ValueError('Invalid activity event fields.')
    payload = {'transport_id': identity, 'cupcake': message}
    locked = type(progress).objects.select_for_update().get(pk=progress.pk)
    practice = isinstance(locked, RecommendationProgress)
    if practice and locked.retired_at:
        raise PermissionDenied('This recommendation has been retired.')
    events = locked.events if practice else ModuleProgressEvent.objects.filter(module_progress=locked)
    if events.filter(source='cupcake', payload__transport_id=identity).exists():
        progress.refresh_from_db()
        return
    score = value = None
    attempt = name == 'answerChecked' and kind in {'code-completion', 'parameterized-code-tracing'}
    if attempt:
        if not isinstance(data.get('isCorrect'), bool):
            raise ValueError('Answer checks must include boolean isCorrect.')
        score = percentage(data['blanksSucceededPercent']) if kind == 'code-completion' and 'blanksSucceededPercent' in data else (100.0 if data['isCorrect'] else 0.0)
        value = score / 100
    elif kind == 'worked-example' and name in {'explanationOpened', 'explanationNavigated'}:
        reported = data.get('progress', {})
        if not isinstance(reported, dict) or 'explanations' not in reported:
            raise ValueError('Explanation events must report viewing progress.')
        value = percentage(reported['explanations']) / 100
    log_module_progress_event(locked, event_type='provider_event', source='cupcake', payload=payload)
    if value is not None and (not attempt or module_accepts_scored_attempt(locked)):
        complete = locked.is_complete or (data['isCorrect'] if attempt else value >= 1)
        apply_progress_snapshot(locked, source='cupcake', progress=max(locked.progress, value),
            score=score, success=data['isCorrect'] if attempt else complete,
            is_complete=complete, payload=payload, event_type='attempt' if attempt else 'progress')
        if attempt:
            locked.attempts += 1
            locked.last_response = json.dumps(payload)
            locked.save(update_fields=['attempts', 'last_response'])
    progress.refresh_from_db()

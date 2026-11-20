"""Read-only, bounded access to course and practice event streams.

Never join full progress/activity objects: their saved state and content can dwarf
the event itself. Payloads are fetched only for inspection or export.
"""
from datetime import datetime, time, timedelta, timezone

from django.core.exceptions import ValidationError
from django.db.models import Q, Count

from courses.models import ModuleAccessLog, ModuleProgressEvent, RecommendationEvent, RecommendationProgress


CONTEXTS = ('course', 'practice', 'access')
COMMON = {'id': 'id', 'time_utc': 'created_at', 'event': 'event_type'}
COURSE = dict(COMMON, student='user__username', student_name='user__full_name',
              email='user__email', student_id='user_id', activity='module__title',
              module_id='module_id', enrollment_id='module_progress__enrollment_id',
              source='source', attempt_score='score', progress='progress', success='success', payload='payload')
PRACTICE = dict(COMMON, student='activation__enrollment__student__username',
                student_name='activation__enrollment__student__full_name', email='activation__enrollment__student__email',
                student_id='activation__enrollment__student_id', enrollment_id='activation__enrollment_id',
                activity='recommendation__module__title', module_id='recommendation__module_id',
                original_problem='activation__source_module__title', source_module_id='activation__source_module_id',
                recommendation_id='recommendation_id', provider='recommendation__provider', rank='recommendation__rank',
                similarity='recommendation__similarity',
                source='source', attempt_score='score', progress='progress', success='success', payload='payload')
ACCESS = dict(COMMON, student='user__username', student_name='user__full_name', email='user__email',
              student_id='user_id', enrollment_id='enrollment_id', activity='module__title',
              module_id='module_id', payload='metadata')
SUMMARY = {key: value for key, value in PRACTICE.items() if key not in ('time_utc', 'event', 'source', 'payload', 'recommendation_id')}
SUMMARY.update(id='id', time_utc='activation__activated_at', activity='module__title', module_id='module_id',
               provider='provider', rank='rank', similarity='similarity', attempt_score='score', progress='progress', success='success',
               attempts='attempts', completed_at='completed_at', feedback='feedback', retired_at='retired_at',
               visits='visits', impressions='impressions', submissions='submissions')
FIELDS = {'course': COURSE, 'practice': PRACTICE, 'access': ACCESS, 'summary': SUMMARY}
CSV_FIELDS = ['context', 'id', 'time_utc', 'student', 'student_name', 'email', 'student_id',
              'enrollment_id', 'module_id', 'activity', 'source_module_id', 'original_problem',
              'recommendation_id', 'provider', 'rank', 'event', 'source', 'attempt_score',
              'progress', 'success', 'payload', 'attempts', 'completed_at', 'feedback', 'retired_at', 'visits', 'impressions',
              'submissions', 'similarity', 'ranking_method']


def filters_from(params):
    result = {key: str(params.get(key, '')).strip()[:200] for key in ('q', 'event', 'from', 'to', 'student', 'module', 'original')}
    for key in ('from', 'to'):
        if result[key]:
            try:
                datetime.strptime(result[key], '%Y-%m-%d')
            except ValueError as exc:
                raise ValidationError('Invalid date filter.') from exc
    if result['from'] and result['to'] and result['from'] > result['to']:
        raise ValidationError('The start date must precede the end date.')
    for key in ('student', 'module', 'original'):
        if result[key] and not result[key].isdigit():
            raise ValidationError('Invalid activity filter.')
    return result


def queryset(instance, context, filters=None):
    instructors = instance.instructors.values('pk')
    if context == 'course':
        qs = ModuleProgressEvent.objects.filter(
            Q(course_instance=instance) |
            Q(course_instance__isnull=True, module_progress__enrollment__course_instance=instance)
        ).exclude(
            module_progress__enrollment__is_instructor_preview=True).exclude(user__in=instructors)
    elif context == 'practice':
        qs = RecommendationEvent.objects.filter(activation__enrollment__course_instance=instance).exclude(
            activation__enrollment__is_instructor_preview=True).exclude(activation__enrollment__student__in=instructors)
    elif context == 'access':
        qs = ModuleAccessLog.objects.filter(course_instance=instance).exclude(
            enrollment__is_instructor_preview=True).exclude(user__in=instructors)
    elif context == 'summary':
        qs = RecommendationProgress.objects.filter(activation__enrollment__course_instance=instance).exclude(
            activation__enrollment__is_instructor_preview=True).exclude(activation__enrollment__student__in=instructors)
    else:
        raise ValidationError('Unknown activity stream.')
    fields = FIELDS[context]
    filters = filters or {}
    if filters.get('q'):
        search = Q()
        for key in ('student', 'student_name', 'email', 'activity', 'original_problem', 'source', 'event'):
            if key in fields:
                search |= Q(**{fields[key] + '__icontains': filters['q']})
        qs = qs.filter(search)
    if filters.get('event') and context != 'summary':
        qs = qs.filter(event_type=filters['event'])
    for key, field in (('student', 'student_id'), ('module', 'module_id')):
        if filters.get(key):
            qs = qs.filter(**{fields[field]: filters[key]})
    if filters.get('original') and context in ('practice', 'summary'):
        qs = qs.filter(activation__source_module_id=filters['original'])
    for key, lookup in (('from', 'created_at__gte'), ('to', 'created_at__lt')):
        if filters.get(key):
            day = datetime.combine(datetime.strptime(filters[key], '%Y-%m-%d').date(), time(), tzinfo=timezone.utc)
            if context == 'summary':
                lookup = lookup.replace('created_at', 'activation__activated_at')
            qs = qs.filter(**{lookup: day + (timedelta(days=1) if key == 'to' else timedelta())})
    return qs


def snapshot(instance, context, filters):
    value = queryset(instance, context, filters).order_by('-pk').values_list('pk', flat=True).first()
    return str(value) if value is not None else None


def rows(instance, context, filters, ceiling, before=None, limit=50, payload=False):
    if ceiling is None:
        return []
    qs = queryset(instance, context, filters).filter(pk__lte=ceiling)
    if before is not None:
        qs = qs.filter(pk__lt=before)
    if context == 'summary':
        ids = list(qs.order_by('-pk').values_list('pk', flat=True)[:limit])
        qs = qs.filter(pk__in=ids).annotate(visits=Count('events', filter=Q(events__event_type='visit')),
                                          impressions=Count('events', filter=Q(events__event_type='impression')),
                                          submissions=Count('events', filter=Q(events__event_type='attempt')))
    fields = {key: value for key, value in FIELDS[context].items() if payload or key != 'payload'}
    if payload and context in ('practice', 'summary'):
        fields['configuration'] = 'activation__configuration'
    result = []
    for row in qs.order_by('-pk').values(*set(fields.values()))[:limit]:
        record = dict(context=context, **{key: row[field] for key, field in fields.items()})
        if 'configuration' in record:
            configuration = record.pop('configuration')
            provenance = configuration.get('provenance') if isinstance(configuration, dict) else []
            provenance = provenance if isinstance(provenance, list) else []
            explicit = any(p.get('ranking') == 'explicit_rank' for p in provenance if isinstance(p, dict))
            record['ranking_method'] = 'explicit_rank' if explicit else 'cosine_similarity'
            if explicit:
                record['similarity'] = None
        result.append(record)
    return result

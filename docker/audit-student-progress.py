"""Read-only evidence report. Feed to manage.py shell; no deployment required.

Defaults to production sessions 42,43. AUDIT_SESSION_IDS can override for testing.
Only SELECT statements are permitted while collecting the report. No progress
services, model saves, grade passback, network calls, or repairs are invoked.
"""
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

from django.db import connection
from django.db.models import Q
from courses.models import (CourseInstance, Enrollment, Module, ModuleProgress,
    ModuleProgressEvent, ModuleAccessLog, CourseProgress,
    RecommendationProgress, RecommendationEvent)


def select_only(execute, sql, params, many, context):
    if not sql.lstrip().upper().startswith('SELECT '):
        raise RuntimeError('Audit blocked a non-SELECT statement')
    return execute(sql, params, many, context)


def evidence(value):
    """Describe retained evidence without disclosing answers or launch tokens."""
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {'submission', 'answer', 'response', 'student_answer',
                               'code', 'last_response'} and child not in (None, '', [], {}):
                found.add(key)
            found.update(evidence(child))
    elif isinstance(value, list):
        for child in value:
            found.update(evidence(child))
    return found


def summarize_events(events):
    types, sources, fields = Counter(), Counter(), set()
    completion_ids, scored_ids = [], []
    last = None
    for event in events:
        types[event['event_type']] += 1
        sources[event['source']] += 1
        fields.update(evidence(event['payload']))
        last = max(last, event['created_at']) if last else event['created_at']
        if event['event_type'] == 'completion' or (event['progress'] or 0) >= 1:
            completion_ids.append(event['id'])
        if event['score'] is not None and event['event_type'] not in {
                'launch', 'iframe_load', 'tab_focus', 'tab_blur', 'provider_event'}:
            scored_ids.append(event['id'])
    return {'types': dict(types), 'sources': dict(sources), 'last_event': last,
            'completion_evidence_event_ids': completion_ids,
            'scored_event_ids': scored_ids, 'answer_field_names': sorted(fields)}


def collect():
    ids = [int(x) for x in os.environ.get('AUDIT_SESSION_IDS', '42,43').split(',')]
    report = {'generated_at': datetime.now(timezone.utc), 'requested_sessions': ids,
              'limits': ['Launch without completion is not proof of lost progress.',
                         'No record cannot distinguish no activity from a lost callback.',
                         'Historical resets or configuration changes can explain discrepancies.',
                         'Live database reads are not a single point-in-time snapshot.'],
              'sessions': []}
    for instance in CourseInstance.objects.filter(pk__in=ids).values('id', 'course_id', 'group_name'):
        enrollments = list(Enrollment.objects.filter(course_instance_id=instance['id']).values(
            'id', 'student_id', 'student__username', 'active'))
        eids = [e['id'] for e in enrollments]
        uids = [e['student_id'] for e in enrollments]
        modules = {m['id']: m for m in Module.objects.filter(unit__course_id=instance['course_id']).values(
            'id', 'title', 'provider_id', 'is_recommendation_only')}
        progress = list(ModuleProgress.objects.filter(enrollment_id__in=eids).values(
            'id', 'enrollment_id', 'module_id', 'score', 'progress', 'attempts',
            'is_complete', 'success', 'last_accessed', 'state_data', 'last_response'))
        events = defaultdict(list)
        for ev in ModuleProgressEvent.objects.filter(Q(course_instance_id=instance['id']) |
                Q(module_progress__enrollment_id__in=eids)).values('id', 'module_progress_id',
                'event_type', 'source', 'score', 'progress', 'payload', 'created_at'):
            events[ev['module_progress_id']].append(ev)
        access = defaultdict(Counter)
        for entry in ModuleAccessLog.objects.filter(course_instance_id=instance['id']).values(
                'user_id', 'module_id', 'event_type'):
            access[(entry['user_id'], entry['module_id'])][entry['event_type']] += 1
        totals = {c['enrollment_id']: c for c in CourseProgress.objects.filter(
            enrollment_id__in=eids).values('enrollment_id', 'modules_completed',
                'total_modules', 'overall_progress', 'overall_score')}
        by_enrollment = defaultdict(dict)
        for p in progress:
            by_enrollment[p['enrollment_id']][p['module_id']] = p
        students = []
        for enrollment in enrollments:
            rows = by_enrollment[enrollment['id']]
            details = []
            for mid in sorted(set(rows) | {m for u, m in access if u == enrollment['student_id']}):
                p = rows.get(mid)
                logs = dict(access[(enrollment['student_id'], mid)])
                summary = summarize_events(events.get(p['id'], []) if p else [])
                flags = []
                if logs.get('launch') and not p:
                    flags.append('launched_without_progress_row')
                if p and summary['completion_evidence_event_ids'] and not p['is_complete']:
                    flags.append('completion_evidence_but_incomplete')
                if p and p['progress'] >= 1 and not p['is_complete']:
                    flags.append('full_progress_but_incomplete')
                if logs.get('launch') and not summary['scored_event_ids'] and not summary['completion_evidence_event_ids'] and not (p and p['is_complete']):
                    flags.append('launch_without_scored_or_completion_event_review_only')
                # Omit untouched pre-created rows, but retain all activity evidence.
                if not (logs or summary['types'] or (p and (p['attempts'] or p['progress'] or p['is_complete'] or p['state_data'] or p['last_response']))):
                    continue
                state_fields = sorted(evidence(p['state_data'])) if p else []
                safe = {k: v for k, v in p.items() if k not in {'state_data', 'last_response'}} if p else None
                details.append({'module': modules.get(mid, {'id': mid}), 'progress': safe,
                    'access_counts': logs, 'events': summary, 'flags': flags,
                    'saved_state_present': bool(p and p['state_data']),
                    'saved_response_present': bool(p and p['last_response']),
                    'state_answer_field_names': state_fields})
            students.append({'username': enrollment['student__username'], 'enrollment_id': enrollment['id'],
                'active': enrollment['active'], 'course_totals': totals.get(enrollment['id']),
                'completed_non_practice_rows': sum(bool(p['is_complete']) for mid, p in rows.items()
                    if not modules.get(mid, {}).get('is_recommendation_only', False)), 'activities': details})
        practice = []
        practice_events = defaultdict(list)
        for event in RecommendationEvent.objects.filter(
                activation__enrollment_id__in=eids, recommendation_id__isnull=False).values(
                'id', 'recommendation_id', 'event_type', 'source', 'score', 'progress', 'payload', 'created_at'):
            practice_events[event['recommendation_id']].append(event)
        for p in RecommendationProgress.objects.filter(activation__enrollment_id__in=eids).values(
                'id', 'activation__enrollment_id', 'activation__source_module_id', 'module_id',
                'score', 'progress', 'attempts', 'is_complete'):
            p['events'] = summarize_events(practice_events[p['id']])
            practice.append(p)
        # These may be legitimate previews/other enrollments; they are not proof of misattribution.
        other = list(ModuleProgress.objects.filter(user_id__in=uids, module_id__in=modules)
            .filter(Q(enrollment__isnull=True) | ~Q(enrollment_id__in=eids))
            .filter(Q(attempts__gt=0) | Q(progress__gt=0) | Q(is_complete=True))
            .values('id', 'user__username', 'module_id', 'enrollment__course_instance_id',
                    'score', 'progress', 'is_complete', 'attempts'))
        instance.update(students=students, recommendation_practice=practice,
                        other_session_or_preview_progress_review_only=other)
        report['sessions'].append(instance)
    report['missing_session_ids'] = sorted(set(ids) - {s['id'] for s in report['sessions']})
    report['flag_counts'] = dict(Counter(flag for s in report['sessions'] for student in s['students']
        for activity in student['activities'] for flag in activity['flags']))
    return report


with connection.execute_wrapper(select_only):
    print(json.dumps(collect(), default=str, indent=2))

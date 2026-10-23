"""Completion-based course grades. Preview and persisted grades use this evaluator."""
from collections import defaultdict
from math import isfinite


def normalize_policy(raw, unit_ids):
    if not isinstance(raw, dict):
        raise ValueError('Invalid grading policy.')
    valid_unit_ids = {str(id) for id in unit_ids}
    def number(value, name, low=0, high=100000):
        try:
            value = float(value)
        except (ValueError, TypeError):
            raise ValueError(f'{name} must be a number.') from None
        if not isfinite(value) or not low <= value <= high:
            raise ValueError(f'{name} must be between {low} and {high}.')
        return value
    mode = raw.get('mode', 'modules')
    if mode not in {'modules', 'units'}:
        raise ValueError('Choose module completion or unit targets.')
    points = raw.get('points')
    result = {
        'mode': mode,
        'points': None if points in (None, '') else number(points, 'Course points', .01),
        'target': number(raw.get('target', 100), 'Completion target', .01, 100),
        'missing_deduction': number(raw.get('missing_deduction', 0), 'Missing-unit deduction'),
        'units': {},
        'groups': [],
    }
    units = raw.get('units', {})
    if not isinstance(units, dict):
        raise ValueError('Invalid unit settings.')
    for key, settings in units.items():
        if str(key) not in valid_unit_ids:
            raise ValueError('A grading unit no longer belongs to this course. Reload the page.')
        if not isinstance(settings, dict):
            raise ValueError('Invalid unit settings.')
        result['units'][str(key)] = {
            'weight': number(settings.get('weight', 1), 'Unit weight'),
            'target': None if settings.get('target') in (None, '') else number(settings['target'], 'Unit target', .01, 100),
            'incomplete_deduction': number(settings.get('incomplete_deduction', 0), 'Incomplete-unit deduction'),
        }
    groups = raw.get('groups', [])
    if not isinstance(groups, list) or len(groups) > 50:
        raise ValueError('Use at most 50 combined completion requirements.')
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get('unit_ids'), list):
            raise ValueError('Invalid combined completion requirement.')
        ids = list(dict.fromkeys(str(id) for id in group['unit_ids']))
        if not ids or not set(ids).issubset(valid_unit_ids):
            raise ValueError('Select course units for each combined requirement.')
        result['groups'].append({'unit_ids': ids, 'deduction': number(group.get('deduction', 0), 'Combined deduction')})
    return result


def eligible_modules(course):
    from courses.models import Module
    return Module.objects.filter(unit__course=course, unit__is_visible=True,
                                 is_visible=True, is_recommendation_only=False).only('id', 'unit_id', 'is_graded')


def calculate_grade(modules, completed_ids, policy):
    """No DB access. Missing progress counts as incomplete; empty units never penalize."""
    units = defaultdict(lambda: {'total': 0, 'completed': 0})
    practice_total = practice_completed = 0
    for module in modules:
        if not module.is_graded:
            practice_total += 1
            practice_completed += module.id in completed_ids
            continue
        units[str(module.unit_id)]['total'] += 1
        units[str(module.unit_id)]['completed'] += module.id in completed_ids
    total = sum(row['total'] for row in units.values())
    completed = sum(row['completed'] for row in units.values())
    progress = 100 * completed / total if total else 0
    weighted = weight_sum = deduction = 0
    missing = []
    penalized = []
    for id, row in units.items():
        settings = policy.get('units', {}).get(id, {})
        weight = settings.get('weight', 1)
        target = settings.get('target') or policy.get('target', 100)
        weighted += min(1, 100 * row['completed'] / row['total'] / target) * weight
        weight_sum += weight
        if not row['completed']:
            missing.append(id)
            deduction += policy.get('missing_deduction', 0)
        if row['completed'] < row['total']:
            penalty = settings.get('incomplete_deduction', 0)
            deduction += penalty
            if penalty:
                penalized.append(id)
    for group in policy.get('groups', []):
        if any(id in units and units[id]['completed'] < units[id]['total'] for id in group['unit_ids']):
            deduction += group['deduction']
    base = (100 * weighted / weight_sum if weight_sum else 0) if policy.get('mode') == 'units' else progress
    maximum = policy.get('points') or 100
    earned = max(0, min(maximum, base * maximum / 100 - deduction))
    return dict(total=total, completed=completed, progress=progress,
                grade=100 * earned / maximum, earned=earned, maximum=maximum,
                base=base, deduction=deduction, units=dict(units),
                missing=missing, penalized=penalized,
                practice_total=practice_total, practice_completed=practice_completed)


def session_results(instance, policy=None, *, enrollments=None):
    from courses.models import Enrollment, ModuleProgress
    modules = list(eligible_modules(instance.course))
    if enrollments is None:
        enrollments = list(Enrollment.objects.filter(course_instance=instance, active=True).select_related('student'))
    completed = defaultdict(set)
    for enrollment_id, module_id in ModuleProgress.objects.filter(
        enrollment__in=enrollments, is_complete=True
    ).values_list('enrollment_id', 'module_id'):
        completed[enrollment_id].add(module_id)
    policy = instance.grading_policy if policy is None else policy
    return [dict(enrollment_id=e.id, name=e.student.get_display_name(), username=e.student.username,
                 **calculate_grade(modules, completed[e.id], policy)) for e in enrollments]


def refresh_course_grades(course):
    for instance in course.instances.all():
        refresh_session_grades(instance)


def refresh_session_grades(instance):
    from courses.models import CourseProgress, Enrollment
    from django.utils import timezone
    enrollments = list(Enrollment.all_objects.filter(course_instance=instance).select_related('student'))
    existing = {p.enrollment_id: p for p in CourseProgress.objects.filter(enrollment__in=enrollments)}
    new, changed = [], []
    for result in session_results(instance, enrollments=enrollments):
        row = existing.get(result['enrollment_id']) or CourseProgress(enrollment_id=result['enrollment_id'])
        row.total_modules = result['total']
        row.modules_completed = result['completed']
        row.overall_progress = result['progress']
        row.overall_score = result['grade']
        row.practice_total = result['practice_total']
        row.practice_completed = result['practice_completed']
        row.completed_at = (row.completed_at or timezone.now()) if result['total'] and result['completed'] == result['total'] else None
        (changed if row.pk else new).append(row)
    CourseProgress.objects.bulk_create(new)
    CourseProgress.objects.bulk_update(changed, ['total_modules', 'modules_completed', 'overall_progress', 'overall_score', 'completed_at', 'practice_total', 'practice_completed'])

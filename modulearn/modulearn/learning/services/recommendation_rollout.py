"""Explicit, audited transitions of already-activated practice assignments."""
from collections import defaultdict
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from courses.models import Course, StaticRecommendationSet, RecommendationActivation, RecommendationProgress, RecommendationEvent
from .recommendation_tracking import select_candidates
from .static_recommendations import resolve_nodes, source_keys_by_module
from .recommendation_sessions import resolve_session


@transaction.atomic
def transition_recommendations(course_id, *, course_instance_id=None, apply=False, expected_plan=None):
    course = Course.objects.select_for_update().get(pk=course_id)
    if course.is_locked_for_research:
        raise ValueError('Research-locked courses cannot be transitioned.')
    instance = resolve_session(course_id, course_instance_id)
    dataset = StaticRecommendationSet.objects.select_for_update().get(course_instance=instance)
    resolved, issues, modules = resolve_nodes(dataset, course)
    if issues:
        raise ValueError(f'Resolve all {len(issues)} missing or ambiguous activities before transitioning.')
    edges_by_source = defaultdict(list)
    edges_by_key = defaultdict(list)
    for edge in dataset.edges:
        edges_by_key[edge['source']].append(edge)
    for module_id, keys in source_keys_by_module(dataset, resolved, modules).items():
        for key in sorted(keys):
            edges_by_source[module_id].extend(edges_by_key[key])
    configuration = {'options': dataset.options, 'provenance': dataset.provenance,
                     'dataset_revision': dataset.updated_at.isoformat(),
                     'failure_threshold': dataset.options.get('failure_threshold', 2),
                     'limit_scope': 'per_activity_type'}
    plans = []
    activations = list(RecommendationActivation.objects.select_for_update().filter(
        enrollment__course_instance=instance, activated_at__isnull=False).order_by('pk'))
    items_by_activation = defaultdict(list)
    for item in RecommendationProgress.objects.select_for_update().filter(
            activation__in=activations).order_by('pk'):
        items_by_activation[item.activation_id].append(item)
    for activation in activations:
        candidates = select_candidates(dataset, resolved, edges_by_source[activation.source_module_id], activation.source_module_id)
        desired = {m.pk: {'provider': edge['provider'], 'rank': edge['rank'], 'similarity': edge['similarity']}
                   for m, edge in candidates}
        existing = items_by_activation[activation.pk]
        before = [{'id': str(i.pk), 'module_id': i.module_id, 'provider': i.provider,
                   'rank': i.rank, 'similarity': i.similarity, 'retired': bool(i.retired_at)} for i in existing]
        # No-op reruns do not add misleading transition events.
        current = {i.module_id: {'provider': i.provider, 'rank': i.rank, 'similarity': i.similarity}
                   for i in existing if not i.retired_at}
        if current == desired and activation.configuration == configuration:
            continue
        plans.append({'activation_id': activation.pk, 'source_module_id': activation.source_module_id,
                      'before_configuration': activation.configuration, 'before': before,
                      'desired': desired})
    document = {'course_id': course.pk, 'course_instance_id': instance.pk, 'configuration': configuration, 'assignments': plans}
    digest = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
    report = {'course_id': course.pk, 'course_instance_id': instance.pk, 'dataset_revision': dataset.updated_at.isoformat(),
              'plan_sha256': digest, 'assignments_changed': len(plans), 'add': 0, 'retire': 0, 'retain': 0, 'restore': 0}
    for plan in plans:
        previous = {i['module_id']: i for i in plan['before']}
        wanted = plan['desired']
        report['add'] += len(set(wanted) - set(previous))
        report['retire'] += sum(not i['retired'] and mid not in wanted for mid, i in previous.items())
        report['restore'] += sum(i['retired'] and mid in wanted for mid, i in previous.items())
        report['retain'] += sum(not i['retired'] and mid in wanted for mid, i in previous.items())
    if not apply:
        return report
    if not expected_plan or expected_plan != digest:
        raise ValueError('Plan changed or --expect-plan is missing. Run the dry-run again and review it.')
    now = timezone.now()
    activation_by_id = {a.pk: a for a in activations}
    for plan in plans:
        activation = activation_by_id[plan['activation_id']]
        wanted = plan['desired']
        existing = {i.module_id: i for i in items_by_activation[activation.pk]}
        for mid, item in existing.items():
            if mid not in wanted and not item.retired_at:
                item.retired_at = now
                item.save(update_fields=['retired_at'])
        for mid, values in wanted.items():
            if mid not in existing:
                RecommendationProgress.objects.create(activation=activation, module_id=mid, **values)
            else:
                item = existing[mid]
                for field, value in values.items():
                    setattr(item, field, value)
                item.retired_at = None
                item.save(update_fields=['provider', 'rank', 'similarity', 'retired_at'])
        activation.configuration = configuration
        activation.save(update_fields=['configuration'])
        RecommendationEvent.objects.create(activation=activation, event_type='dataset_transition', source='instructor_rollout',
            payload={'plan_sha256': digest, **plan, 'after_configuration': configuration})
    return {**report, 'applied': True}

"""Persistent instructor activity testing, excluded from student enrollment lists."""
from django.db import transaction
from django.utils import timezone
from courses.models import Enrollment, RecommendationActivation, RecommendationProgress


def testing_enrollment(user, instance):
    if not instance.instructors.filter(pk=user.pk).exists():
        return None
    enrollment, _ = Enrollment.all_objects.get_or_create(student=user, course_instance=instance,
        defaults={'is_instructor_preview': True})
    if not enrollment.is_instructor_preview:
        enrollment.is_instructor_preview = True
        enrollment.save(update_fields=['is_instructor_preview'])
    return enrollment


@transaction.atomic
def prepare_recommendations(enrollment, module, dataset):
    from .static_recommendations import resolve_nodes, source_keys_by_module
    from .recommendation_tracking import select_candidates
    resolved, _, modules = resolve_nodes(dataset, module.unit.course)
    keys = source_keys_by_module(dataset, resolved, modules).get(module.pk, set())
    edges = [edge for edge in dataset.edges if edge['source'] in keys]
    candidates = select_candidates(dataset, resolved, edges, module.pk)
    activation, _ = RecommendationActivation.objects.get_or_create(enrollment=enrollment, source_module=module)
    activation = RecommendationActivation.objects.select_for_update().get(pk=activation.pk)
    # Instructor assignments are available immediately, not fictional failures.
    if not activation.activated_at:
        activation.activated_at = timezone.now()
        activation.configuration = {'instructor_testing': True, 'options': dataset.options}
        activation.save(update_fields=['activated_at', 'configuration'])
    RecommendationProgress.objects.filter(activation=activation, retired_at__isnull=True).exclude(
        module_id__in=[target.pk for target, _ in candidates]).update(retired_at=timezone.now())
    for target, edge in candidates:
        RecommendationProgress.objects.update_or_create(activation=activation, module=target,
            defaults={'provider': edge['provider'], 'rank': edge['rank'], 'similarity': edge['similarity'], 'retired_at': None})

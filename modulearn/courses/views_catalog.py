"""Instructor-only catalog search and metadata, scoped to a course session."""
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from courses.models import CourseInstance
from modulearn.learning.services.slc_catalog import SOURCES, CatalogUnavailable, catalog_item, catalog_items


def _authorize(request, instance_id):
    from courses.views import _is_course_instructor
    instance = get_object_or_404(CourseInstance, pk=instance_id)
    if not _is_course_instructor(request.user, instance):
        raise PermissionDenied('Only instructors can browse content for this course.')


@login_required
@require_GET
def search(request, instance_id):
    _authorize(request, instance_id)
    try:
        if request.GET.get('source') and request.GET['source'] not in SOURCES:
            raise ValueError('Choose a valid catalog.')
        items, warnings = catalog_items()
        fields = ('source', 'provider', 'type', 'languages', 'content_languages', 'protocols', 'license')
        def values(item, field):
            value = item[field]
            return set(value if isinstance(value, list) else [value])
        # Keep the complete option universe, even when a search/filter rules an
        # option out. Its zero count explains why it cannot currently be picked.
        choices = {field: {value for item in items for value in values(item, field) if value}
                   for field in fields}
        selected = {field: request.GET.get(field, '') for field in fields}
        for field, value in selected.items():
            if value:
                choices[field].add(value)
        query = request.GET.get('q', '').strip().casefold()[:300]
        if query:
            terms = query.split()
            items = [item for item in items if all(term in ' '.join([
                item['title'], item['description'], item['provider'], item['type'], item['id'],
                *item['authors'], *item['tags'], *item['concepts'], *item['languages'],
            ]).casefold() for term in terms)]
        facets, facet_totals = {}, {}
        def matches(item, excluding=None):
            return all(not value or field == excluding or value in values(item, field)
                       for field, value in selected.items())
        for field in fields:
            # Switching a dropdown replaces its current choice, while retaining
            # the search and every other filter (independent of filter order).
            candidates = [item for item in items if matches(item, excluding=field)]
            counts = Counter(value for item in candidates for value in values(item, field) if value)
            facets[field] = [{'value': value, 'label': SOURCES.get(value, value) if field == 'source' else value,
                              'count': counts[value]} for value in sorted(choices[field])]
            facet_totals[field] = len(candidates)
        items = [item for item in items if matches(item)]
        sort = request.GET.get('sort', 'title')
        if sort == 'newest':
            items.sort(key=lambda item: (item['updated'], item['title'].casefold()), reverse=True)
        else:
            key = sort if sort in {'provider', 'type'} else 'title'
            items.sort(key=lambda item: (str(item[key]).casefold(), item['title'].casefold(), item['source'], item['id']))
        page = max(1, int(request.GET.get('page', 1)))
        total = len(items)
        pages = max(1, (total + 23) // 24)
        page = min(page, pages)
        result = items[(page - 1) * 24:page * 24]
        # Keep full descriptions and concept lists for detail, not each result card.
        summaries = [{**item, 'description': item['description'][:220], 'concepts': item['concepts'][:8]} for item in result]
        return JsonResponse({'items': summaries, 'total': total, 'page': page, 'pages': pages,
                             'facets': facets, 'facet_totals': facet_totals, 'warnings': warnings})
    except CatalogUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@login_required
@require_GET
def detail(request, instance_id):
    _authorize(request, instance_id)
    try:
        return JsonResponse(catalog_item(request.GET.get('source'), request.GET.get('id', '')))
    except CatalogUnavailable as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

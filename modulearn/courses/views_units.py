import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from .models import CourseInstance, Unit
from .views import _is_course_instructor
from .views_grading import check_structure_edit
from modulearn.learning.services.unit_packages import export_unit, import_unit


def owned_instance(request, instance_id):
    instance = get_object_or_404(CourseInstance.objects.select_related('course'), pk=instance_id)
    if not _is_course_instructor(request.user, instance):
        raise PermissionDenied
    return instance


@login_required
@require_GET
def export(request, instance_id, unit_id):
    instance = owned_instance(request, instance_id)
    unit = get_object_or_404(Unit, pk=unit_id, course=instance.course)
    response = JsonResponse(export_unit(unit), json_dumps_params={'indent': 2})
    response['Content-Disposition'] = f'attachment; filename="modulearn-unit-{unit.id}.json"'
    return response


@login_required
@require_POST
def upload(request, instance_id):
    instance = owned_instance(request, instance_id)
    check_structure_edit(instance.course)
    try:
        upload = request.FILES.get('unit_file')
        if not upload or upload.size > 20 * 1024 * 1024:
            raise ValueError('Choose a unit JSON file smaller than 20 MB.')
        unit, warnings = import_unit(instance.course, json.loads(upload.read()))
        messages.success(request, f'Imported {unit.title} as a new unit.')
        for warning in warnings:
            messages.warning(request, warning)
    except (ValueError, TypeError, KeyError) as exc:
        messages.error(request, str(exc))
    return redirect('courses:course_configuration', instance_id=instance.id)

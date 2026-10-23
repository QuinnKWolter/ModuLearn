from django.db import migrations
from django.utils import timezone


def refresh_fallback(apps, schema_editor):
    from modulearn.learning.services.grading import calculate_grade
    Module = apps.get_model('courses', 'Module')
    Instance = apps.get_model('courses', 'CourseInstance')
    Progress = apps.get_model('courses', 'ModuleProgress')
    CourseProgress = apps.get_model('courses', 'CourseProgress')
    alias = schema_editor.connection.alias
    for instance in Instance.objects.using(alias).iterator():
        modules = list(Module.objects.using(alias).filter(unit__course_id=instance.course_id,
            is_visible=True, unit__is_visible=True, is_recommendation_only=False))
        if any(module.is_graded for module in modules):
            continue
        completed = {}
        for eid, mid in Progress.objects.using(alias).filter(enrollment__course_instance_id=instance.id,
            is_complete=True).values_list('enrollment_id','module_id'):
            completed.setdefault(eid,set()).add(mid)
        rows = list(CourseProgress.objects.using(alias).filter(enrollment__course_instance_id=instance.id))
        for row in rows:
            result = calculate_grade(modules, completed.get(row.enrollment_id,set()), instance.grading_policy or {})
            row.total_modules, row.modules_completed = result['total'], result['completed']
            row.overall_progress, row.overall_score = result['progress'], result['grade']
            row.practice_total = row.practice_completed = 0
            row.completed_at = (row.completed_at or timezone.now()) if result['total'] and result['completed']==result['total'] else None
        CourseProgress.objects.using(alias).bulk_update(rows,['total_modules','modules_completed',
            'overall_progress','overall_score','practice_total','practice_completed','completed_at'])


class Migration(migrations.Migration):
    dependencies = [('courses','0028_courseinstance_grading_policy_module_is_graded_and_more')]
    operations = [migrations.RunPython(refresh_fallback, migrations.RunPython.noop)]

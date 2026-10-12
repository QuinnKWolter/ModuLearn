from django.db import migrations, models
import django.db.models.deletion


def copy_to_sessions(apps, schema_editor):
    Dataset = apps.get_model('courses', 'StaticRecommendationSet')
    Instance = apps.get_model('courses', 'CourseInstance')
    for original in Dataset.objects.filter(course_instance__isnull=True).select_related('course').iterator():
        enabled = bool((original.course.plugin_config or {}).get('plugins', {}).get('static_recommendations', {}).get('enabled', False))
        for instance in Instance.objects.filter(course_id=original.course_id).iterator():
            Dataset.objects.create(course_id=original.course_id, course_instance_id=instance.pk, enabled=enabled,
                **{name: getattr(original, name) for name in ['nodes','edges','analysis','bindings','options','provenance']})
        # Preserve the old row as a disabled archive, never a fallback for new sessions.
        original.enabled = False
        original.save(update_fields=['enabled'])


class Migration(migrations.Migration):
    dependencies = [('courses', '0025_module_recommendation_only')]
    operations = [
        migrations.AlterField(model_name='staticrecommendationset', name='course',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recommendation_sets', to='courses.course')),
        migrations.AddField(model_name='staticrecommendationset', name='course_instance',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='static_recommendations', to='courses.courseinstance')),
        migrations.AddField(model_name='staticrecommendationset', name='enabled', field=models.BooleanField(default=True)),
        migrations.RunPython(copy_to_sessions),
    ]

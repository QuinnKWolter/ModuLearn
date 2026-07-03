from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0010_course_plugin_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModuleBranchRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('condition_type', models.CharField(choices=[('success', 'Correct / Successful'), ('failure', 'Incorrect / Unsuccessful'), ('completed', 'Completed'), ('score_gte', 'Score At Least'), ('score_lt', 'Score Below')], max_length=32)),
                ('threshold', models.FloatField(blank=True, null=True)),
                ('priority', models.PositiveIntegerField(default=0)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_rules', to='courses.course')),
                ('source_module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_source_rules', to='courses.module')),
                ('target_module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_target_rules', to='courses.module')),
            ],
            options={
                'ordering': ['source_module_id', 'priority', 'id'],
                'indexes': [
                    models.Index(fields=['course', 'active'], name='branch_course_active_idx'),
                    models.Index(fields=['source_module', 'active'], name='branch_source_active_idx'),
                    models.Index(fields=['target_module', 'active'], name='branch_target_active_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='EnrollmentModuleUnlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(blank=True, max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('enrollment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dynamic_module_unlocks', to='courses.enrollment')),
                ('module', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dynamic_unlocks', to='courses.module')),
                ('source_module', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dynamic_unlock_sources', to='courses.module')),
                ('source_rule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='unlock_events', to='courses.modulebranchrule')),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('enrollment', 'module', 'source_rule')},
                'indexes': [
                    models.Index(fields=['enrollment', 'module'], name='unlock_enroll_module_idx'),
                    models.Index(fields=['source_rule', 'created_at'], name='unlock_rule_created_idx'),
                ],
            },
        ),
    ]

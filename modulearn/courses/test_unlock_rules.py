import json
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress, ModuleAccessLog
from courses.utils import export_course_to_json, create_course_from_json
from modulearn.learning.services.access_rules import evaluate_unit_access, evaluate_module_access, _previous_unit, _previous_module
from modulearn.learning.services.unit_packages import export_unit, import_unit


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
                            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}})
class UnlockRuleTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='unlock-teacher', is_instructor=True)
        self.student = User.objects.create_user(username='unlock-student')
        self.course = Course.objects.create(id='unlock-rules', title='Unlock rules')
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Test')
        self.instance.instructors.add(self.teacher)
        self.units = [Unit.objects.create(course=self.course, title=f'Unit {i}', order=i * 10) for i in range(3)]
        self.activities = [Module.objects.create(unit=unit, title=f'Activity {i}', order=i * 10)
                           for unit in self.units for i in range(2)]
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)
        self.url = reverse('courses:course_configuration', args=[self.instance.pk])
        self.client.force_login(self.teacher)

    def fields(self):
        fields = {}
        for item in [*self.units, *self.activities]:
            prefix = ('unit' if isinstance(item, Unit) else 'module') + f'_{item.pk}'
            fields.update({prefix + '_visible': '1', prefix + '_order': str(item.order),
                           prefix + '_locked': str(int(item.is_locked)), prefix + '_rule_type': item.unlock_rule_type,
                           prefix + '_rule_target': str(item.unlock_rule_target)})
        return fields

    def post(self, fields):
        return self.client.post(self.url, {'action': 'update_structure', 'structure_controls': json.dumps(list(fields.items()))})

    def rule(self, item, kind, target=None):
        item.is_locked = True
        item.unlock_rule = {'conditions': [dict(type=kind, **({'target_id': target.pk} if target else {}))]}
        item.save(update_fields=['is_locked', 'unlock_rule'])

    def test_previous_activity_access_and_completion_are_distinct(self):
        first, second = self.activities[:2]
        self.rule(second, 'previous_module_completed')
        self.assertFalse(evaluate_module_access(second, self.enrollment).can_access)
        ModuleAccessLog.objects.create(user=self.student, enrollment=self.enrollment, course_instance=self.instance,
                                       module=first, event_type=ModuleAccessLog.EVENT_LAUNCH)
        self.assertFalse(evaluate_module_access(second, self.enrollment).can_access)
        self.rule(second, 'previous_module_accessed')
        self.assertTrue(evaluate_module_access(second, self.enrollment).can_access)
        self.rule(second, 'previous_module_completed')
        ModuleProgress.objects.filter(module=first, enrollment=self.enrollment).update(is_complete=True)
        self.assertTrue(evaluate_module_access(second, self.enrollment).can_access)

    def test_previous_activity_crosses_units_skips_hidden_practice_library_and_follows_order(self):
        unit = self.units[1]
        self.rule(unit, 'previous_module_completed')
        previous = self.activities[1]
        self.assertEqual(_previous_module(subject_unit=unit), previous)
        self.assertEqual(_previous_module(subject_module=self.activities[2]), previous)
        self.assertFalse(evaluate_unit_access(unit, self.enrollment).can_access)
        ModuleProgress.objects.filter(module=previous, enrollment=self.enrollment).update(is_complete=True)
        self.assertTrue(evaluate_unit_access(unit, self.enrollment).can_access)
        Module.objects.create(unit=self.units[0], title='Hidden', order=500, is_visible=False)
        Module.objects.create(unit=self.units[0], title='Recommendations', order=600, is_recommendation_only=True)
        hidden_unit = Unit.objects.create(course=self.course, title='Hidden unit', order=5, is_visible=False)
        Module.objects.create(unit=hidden_unit, title='Hidden unit activity')
        self.assertEqual(_previous_module(subject_unit=unit), previous)
        self.activities[0].order = 20
        self.activities[0].save(update_fields=['order'])
        self.assertEqual(_previous_module(subject_unit=unit), self.activities[0])
        self.assertFalse(evaluate_unit_access(unit, self.enrollment).can_access)

    def test_previous_unit_uses_order_then_id_for_ties(self):
        self.units[2].order = self.units[1].order
        self.units[2].save(update_fields=['order'])
        self.assertEqual(_previous_unit(self.units[2]), self.units[1])
        self.assertEqual(_previous_module(subject_unit=self.units[2]), self.activities[3])

    def test_selected_unit_access_requires_all_activities_and_completion_requires_completed(self):
        target, subject = self.units[0], self.units[2]
        self.rule(subject, 'unit_accessed', target)
        self.rule(self.activities[-1], 'unit_completed', target)
        for index, activity in enumerate(self.activities[:2]):
            self.assertFalse(evaluate_unit_access(subject, self.enrollment).can_access)
            ModuleAccessLog.objects.create(user=self.student, enrollment=self.enrollment, course_instance=self.instance,
                                           module=activity, event_type=ModuleAccessLog.EVENT_LAUNCH)
            self.assertFalse(evaluate_module_access(self.activities[-1], self.enrollment).can_access)
            ModuleProgress.objects.filter(enrollment=self.enrollment, module=activity).update(is_complete=True)
        self.assertTrue(evaluate_unit_access(subject, self.enrollment).can_access)
        self.assertTrue(evaluate_module_access(self.activities[-1], self.enrollment).can_access)

    def test_configuration_saves_each_new_rule_for_units_and_activities(self):
        for kind in ['previous_module_accessed', 'previous_module_completed', 'unit_accessed', 'unit_completed']:
            with self.subTest(kind=kind):
                fields = self.fields()
                for prefix in (f'unit_{self.units[2].pk}', f'module_{self.activities[-1].pk}'):
                    fields[prefix + '_rule_type'] = kind
                    fields[prefix + '_rule_target'] = str(self.units[0].pk)
                self.assertRedirects(self.post(fields), self.url)
                for item in (self.units[2], self.activities[-1]):
                    item.refresh_from_db()
                    self.assertTrue(item.is_locked)
                    self.assertEqual(item.unlock_rule_type, kind)
                    self.assertEqual(item.unlock_rule_target, self.units[0].pk if kind.startswith('unit_') else '')

    def test_invalid_selected_unit_is_rejected_atomically_including_submitted_reordering(self):
        foreign = Unit.objects.create(course=Course.objects.create(id='foreign', title='Foreign'), title='Foreign')
        for target in (self.units[1], self.units[2], foreign):
            fields = self.fields()
            fields.update({f'unit_{self.units[0].pk}_title': 'Must roll back',
                           f'unit_{self.units[1].pk}_rule_type': 'unit_completed',
                           f'unit_{self.units[1].pk}_rule_target': str(target.pk)})
            self.assertRedirects(self.post(fields), self.url)
            self.units[0].refresh_from_db()
            self.assertEqual(self.units[0].title, 'Unit 0')
        fields = self.fields()
        fields.update({f'unit_{self.units[1].pk}_rule_type': 'unit_completed',
                       f'unit_{self.units[1].pk}_rule_target': str(self.units[0].pk),
                       f'unit_{self.units[0].pk}_order': '100'})
        self.assertRedirects(self.post(fields), self.url)
        self.units[0].refresh_from_db()
        self.assertEqual(self.units[0].order, 0)

    def test_course_roundtrip_remaps_selected_units_and_retains_relative_activity_rules(self):
        self.rule(self.units[2], 'unit_completed', self.units[0])
        self.rule(self.activities[-1], 'unit_accessed', self.units[0])
        self.rule(self.activities[3], 'previous_module_completed')
        data = export_course_to_json(self.course)
        data['id'] = 'copied-rules'
        imported = create_course_from_json(data, self.teacher)
        units = list(imported.units.all())
        self.assertNotEqual(units[0].pk, self.units[0].pk)
        self.assertEqual(units[2].unlock_rule_target, units[0].pk)
        self.assertEqual(units[2].modules.last().unlock_rule_target, units[0].pk)
        self.assertEqual(units[1].modules.last().unlock_rule_type, 'previous_module_completed')

    def test_unit_package_requires_reselecting_external_unit_and_keeps_previous_activity_rule(self):
        self.rule(self.units[1], 'unit_completed', self.units[0])
        self.rule(self.activities[3], 'previous_module_completed')
        unit, warnings = import_unit(self.course, export_unit(self.units[1]))
        self.assertTrue(warnings)
        self.assertEqual(unit.unlock_rule_type, 'unresolved_import')
        self.assertFalse(evaluate_unit_access(unit, self.enrollment).can_access)
        self.assertEqual(unit.modules.last().unlock_rule_type, 'previous_module_completed')

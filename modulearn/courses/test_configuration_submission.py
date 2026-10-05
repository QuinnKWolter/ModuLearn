import json
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import Course, CourseInstance, Module, Unit


@override_settings(STORAGES={'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
                            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}})
class ConfigurationSubmissionTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='config-teacher', is_instructor=True)
        self.course = Course.objects.create(id='large-config', title='Configuration')
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='Configuration')
        self.instance.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Original unit', order=1)
        self.first = Module.objects.create(unit=self.unit, title='First', order=1, content_url='https://example.org/first')
        self.second = Module.objects.create(unit=self.unit, title='Second', order=2)
        self.url = reverse('courses:course_configuration', args=[self.instance.pk])
        self.client.force_login(self.teacher)

    def fields(self):
        fields = [(f'unit_{self.unit.pk}_visible', '1')]
        for module in self.unit.modules.all():
            fields.extend([
                (f'module_{module.pk}_title', module.title),
                (f'module_{module.pk}_order', str(module.order)),
                (f'module_{module.pk}_visible', '1'),
                (f'module_{module.pk}_unit_id', str(self.unit.pk)),
            ])
        return dict(fields)

    def post(self, fields, **extra):
        return self.client.post(self.url, {
            'action': 'update_structure', 'structure_controls': json.dumps(list(fields.items())), **extra,
        })

    def test_large_course_can_reorder_and_hide_without_raising_global_field_limit(self):
        Module.objects.bulk_create([
            Module(unit=self.unit, title=f'Extra {i}', order=i + 3) for i in range(262)
        ])
        fields = self.fields()
        self.assertGreater(len(fields), settings.DATA_UPLOAD_MAX_NUMBER_FIELDS)
        fields[f'module_{self.first.pk}_order'] = '2'
        fields[f'module_{self.second.pk}_order'] = '1'
        fields[f'module_{self.first.pk}_visible'] = '0'
        response = self.post(fields)
        self.assertRedirects(response, self.url)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.order, 2)
        self.assertEqual(self.second.order, 1)
        self.assertFalse(self.first.is_visible)
        self.assertTrue(self.second.is_visible)
        self.assertEqual(self.first.content_url, 'https://example.org/first')
        self.assertEqual(self.unit.modules.filter(is_visible=True).count(), 263)

    def test_failed_save_rolls_back_prior_edits_and_deletions(self):
        fields = self.fields()
        fields[f'unit_{self.unit.pk}_title'] = 'Should roll back'
        fields[f'module_{self.first.pk}_delete'] = '1'
        fields[f'module_{self.second.pk}_order'] = 'invalid'
        response = self.post(fields)
        self.assertRedirects(response, self.url)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.title, 'Original unit')
        self.assertTrue(Module.objects.filter(pk=self.first.pk).exists())

    def test_packed_controls_preserve_file_uploads(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.post(self.fields(), **{
                f'module_{self.first.pk}_content_file': SimpleUploadedFile('example.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
            })
            self.assertEqual(response.status_code, 302)
            self.first.refresh_from_db()
            with self.first.content_file.open('rb') as uploaded:
                self.assertEqual(uploaded.read(), b'%PDF-1.4 test')

    def test_malformed_payload_does_not_change_configuration(self):
        for packed in ('{', '{}', '[["action", "delete"]]', '[["module_1_title", null]]'):
            with self.subTest(packed=packed):
                response = self.client.post(self.url, {'action': 'update_structure', 'structure_controls': packed})
                self.assertRedirects(response, self.url)
                self.first.refresh_from_db()
                self.assertTrue(self.first.is_visible)
                self.assertEqual(self.first.title, 'First')

    def test_student_cannot_save_packed_configuration(self):
        self.client.force_login(User.objects.create_user(username='config-student'))
        self.assertEqual(self.post(self.fields()).status_code, 403)

    def test_packed_submission_still_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        data = {'action': 'update_structure', 'structure_controls': json.dumps(list(self.fields().items()))}
        self.assertEqual(client.post(self.url, data).status_code, 403)
        client.get(self.url)
        data['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        self.assertEqual(client.post(self.url, data).status_code, 302)

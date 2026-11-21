import json
from html import unescape
import re
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from courses.models import Course, Unit, Module, ModuleProgress, ModuleProgressEvent, Enrollment, ModuleFormSubmission


class InteractiveAuthoringPreviewTests(TestCase):
    def setUp(self):
        self.teacher = get_user_model().objects.create_user(username='preview-author', is_instructor=True)
        self.other = get_user_model().objects.create_user(username='other-author', is_instructor=True)
        self.course = Course.objects.create(id='preview-course', title='Preview')
        self.course.instructors.add(self.teacher)
        self.unit = Unit.objects.create(course=self.course, title='Unit', order=1)
        self.module = Module.objects.create(unit=self.unit, title='Exercise', module_type='splice_smart_content',
            content_url='https://adapt2.sis.pitt.edu/cupcake/', supported_protocols=['splice'])
        self.client.force_login(self.teacher)

    def counts(self):
        return [model.objects.count() for model in (Module, Enrollment, ModuleProgress, ModuleProgressEvent, ModuleFormSubmission)]

    def preview(self, **extra):
        data = {'title':'Unsaved title', 'moduleId':str(self.module.pk), 'activityType':'splice_smart_content',
                'contentUrl':self.module.content_url, 'providerId':'cupcake', 'protocols':'splice', **extra}
        return self.client.post(reverse('recruitment:text_preview'), {'activity':json.dumps(data)})

    def test_interactive_draft_uses_unsaved_url_and_no_course_tracking(self):
        before = self.counts()
        response = self.preview(contentUrl='https://adapt2.sis.pitt.edu/cupcake/?module_id=12&course_instance_id=59&grp=real&usr=student&cid=real&sid=real')
        self.assertEqual(response.status_code, 200)
        launch = unescape(re.search(r'<iframe[^>]+src="([^"]+)"',response.json()['html']).group(1))
        rendered = self.client.get(launch)
        self.assertEqual(rendered.status_code, 200)
        html = rendered.content.decode()
        self.assertIn('previewMode: "true"', html)
        self.assertIn('progressUrl: ""', html)
        iframe = unescape(re.search(r'<iframe[^>]+src="([^"]+)"',html).group(1))
        for value in ('module_id=', 'course_instance_id=', 'usr=student', 'grp=real', 'sid=real'):
            self.assertNotIn(value, iframe)
        self.assertIn('grp=preview', iframe)
        self.assertIn('usr=preview-', iframe)
        self.assertEqual(self.counts(), before)
        self.module.refresh_from_db()
        self.assertEqual(self.module.content_url, 'https://adapt2.sis.pitt.edu/cupcake/')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(launch).status_code,403)
        self.assertEqual(self.preview().status_code,403)

    def test_new_activity_preview_needs_no_database_module(self):
        before = self.counts()
        response = self.preview(moduleId=None)
        launch = unescape(re.search(r'<iframe[^>]+src="([^"]+)"',response.json()['html']).group(1))
        self.assertEqual(self.client.get(launch).status_code,200)
        self.assertEqual(self.counts(),before)

    def test_invalid_urls_tokens_and_unsaved_lti(self):
        self.assertEqual(self.preview(contentUrl='javascript:alert(1)').status_code,400)
        self.assertEqual(self.client.get(reverse('courses:authoring_preview_launch'),{'token':'invalid'}).status_code,400)
        response = self.preview(contentUrl='https://provider.example/lti/launch',protocols='lti')
        self.assertIn('Save this LTI activity', response.json()['html'])
        self.assertNotIn('<iframe', response.json()['html'])

from django.conf import settings
from django.test import TestCase
from lti.models import LTIPlatformRegistration
from lti.platforms import get_lti13_config_dict


class PlatformDefaultsTests(TestCase):
    def test_no_builtin_test_platform_but_registered_lms_is_retained(self):
        self.assertEqual(settings.LTI_CONFIG, {})
        self.assertEqual(get_lti13_config_dict(), {})
        LTIPlatformRegistration.objects.create(name='Test LMS', issuer='https://lms.example.edu',
            client_id='client', deployment_ids=['deployment'],
            auth_login_url='https://lms.example.edu/login', auth_token_url='https://lms.example.edu/token',
            key_set_url='https://lms.example.edu/keys')
        self.assertEqual(set(get_lti13_config_dict()), {'https://lms.example.edu'})

from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase
from accounts.models import User
from courses.views import _unique_generated_student_username

class ShortRosterNamesTests(TestCase):
    def test_compact_session_code_cycles_without_early_repeats(self):
        alphabet='23456789abcdefghjkmnpqrstuvwxyz'
        with patch('courses.views.get_random_string',return_value='abcd'):
            names=[_unique_generated_student_username(SimpleNamespace(id=i),'ns') for i in range(1,len(alphabet)**2+2)]
        self.assertEqual(len(names[0]),9)
        self.assertEqual(names[0].count('-'),1)
        self.assertEqual(len(set(names[:-1])),len(alphabet)**2)
        self.assertEqual(names[0],names[-1])

    def test_collision_retries_and_existing_accounts_unchanged(self):
        instance=SimpleNamespace(id=43)
        with patch('courses.views.get_random_string',return_value='abcd'):
            name=_unique_generated_student_username(instance,'ns')
        user=User.objects.create(username=name)
        with patch('courses.views.get_random_string',side_effect=['abcd','wxyz']) as random:
            next_name=_unique_generated_student_username(instance,'ns')
        self.assertEqual(random.call_count,2)
        self.assertEqual(name[:-4],next_name[:-4])
        user.refresh_from_db();self.assertEqual(user.username,name)

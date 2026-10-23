import json
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from courses.models import Course, CourseInstance, Unit, Module, Enrollment, ModuleProgress
from modulearn.learning.services.grading import calculate_grade, normalize_policy, refresh_session_grades
from modulearn.learning.services.progress import recompute_course_progress
from modulearn.learning.services.access_rules import evaluate_unit_access, evaluate_module_access
from modulearn.learning.services.unit_packages import export_unit, import_unit


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class GradingAndUnitTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='teacher', is_instructor=True)
        self.student = User.objects.create_user(username='student')
        self.course = Course.objects.create(id='grading', title='Grading course')
        self.course.instructors.add(self.teacher)
        self.instance = CourseInstance.objects.create(course=self.course, group_name='A')
        self.instance.instructors.add(self.teacher)
        self.units = [Unit.objects.create(course=self.course, title=f'Unit {i}', order=i) for i in range(2)]
        self.modules = [Module.objects.create(unit=unit, title=f'Exercise {i}', content_url='https://example.org/exercise') for unit in self.units for i in range(4)]
        self.enrollment = Enrollment.objects.create(student=self.student, course_instance=self.instance)

    def test_unit_targets_points_and_combined_deductions(self):
        policy = normalize_policy({'mode':'units', 'points':5, 'target':50, 'missing_deduction':1,
            'units':{str(self.units[0].id):{'incomplete_deduction':1}}}, [u.id for u in self.units])
        completed = {self.modules[i].id for i in [0,1,4,5]}
        result = calculate_grade(self.modules, completed, policy)
        self.assertEqual(result['progress'], 50)
        self.assertEqual(result['earned'], 4) # Both targets met, selected unit not fully complete.
        result = calculate_grade(self.modules, {self.modules[0].id}, policy)
        self.assertEqual(result['earned'], 0) # 1.25 before two deductions, clamped at zero.

    def test_practice_and_hidden_modules_do_not_count_but_keep_scores(self):
        practice = self.modules[0]
        practice.is_graded = False
        practice.save()
        self.modules[1].is_visible = False
        self.modules[1].save()
        row = ModuleProgress.objects.get(enrollment=self.enrollment, module=practice)
        row.is_complete = True
        row.score = 92
        row.save()
        result = recompute_course_progress(self.enrollment)
        self.assertEqual(result.total_modules, 6)
        self.assertEqual(result.overall_score, 0)
        row.refresh_from_db()
        self.assertEqual(row.score, 92)
        self.assertTrue(row.is_complete)

    def test_default_grade_is_completion_not_exercise_score(self):
        ModuleProgress.objects.filter(enrollment=self.enrollment, module=self.modules[0]).update(is_complete=True, score=20)
        result = recompute_course_progress(self.enrollment)
        self.assertEqual(result.overall_score, 12.5)
        self.assertEqual(result.overall_progress, 12.5)

    def test_empty_units_and_zero_weight_are_finite(self):
        policy = normalize_policy({'mode':'units','missing_deduction':3,'units':{str(u.id):{'weight':0} for u in self.units}}, [u.id for u in self.units])
        self.assertEqual(calculate_grade([], set(), policy)['grade'], 0)
        self.assertEqual(calculate_grade(self.modules, set(), policy)['grade'], 0)
        for value in [float('nan'),float('inf'),-1]:
            with self.assertRaises(ValueError):
                normalize_policy({'target':value}, [])

    def test_combined_requirement_deducts_once_not_once_per_unit(self):
        policy = normalize_policy({'mode':'units','points':5,'target':50,
            'groups':[{'unit_ids':[u.id for u in self.units],'deduction':1}]}, [u.id for u in self.units])
        result=calculate_grade(self.modules,{self.modules[i].id for i in [0,1,4,5]},policy)
        self.assertEqual(result['earned'],4)
        self.assertEqual(result['deduction'],1)
        result=calculate_grade(self.modules,{m.id for m in self.modules},policy)
        self.assertEqual(result['earned'],5)

    def test_preview_does_not_save_and_save_is_session_scoped(self):
        other = CourseInstance.objects.create(course=self.course, group_name='B')
        Enrollment.objects.create(student=self.student, course_instance=other)
        self.client.force_login(self.teacher)
        url = reverse('courses:grading', args=[self.instance.id])
        data = {'policy':{'mode':'units','points':5,'target':50}}
        response = self.client.post(url, json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.grading_policy,{})
        response = self.client.post(url, json.dumps(dict(data,save=True)), content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.instance.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(self.instance.grading_policy['points'],5)
        self.assertEqual(other.grading_policy,{})

    def test_teacher_preview_excluded_and_student_cannot_configure(self):
        Enrollment.all_objects.create(student=self.teacher,course_instance=self.instance,is_instructor_preview=True)
        self.client.force_login(self.teacher)
        url=reverse('courses:grading',args=[self.instance.id])
        response=self.client.post(url,json.dumps({'policy':{}}),content_type='application/json')
        self.assertEqual(len(response.json()['rows']),1)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.get(reverse('courses:export_unit',args=[self.instance.id,self.units[0].id])).status_code,403)

    def test_date_boundaries_override_dynamic_unlock(self):
        unit=self.units[0]; now=timezone.now()
        unit.opens_at=now; unit.closes_at=now+timedelta(days=1)
        with patch('modulearn.learning.services.access_rules.timezone.now',return_value=now-timedelta(seconds=1)):
            state=evaluate_unit_access(unit,self.enrollment)
            self.assertFalse(state.can_access)
            with patch('modulearn.learning.services.access_rules._has_dynamic_module_unlock',return_value=True):
                self.assertFalse(evaluate_module_access(self.modules[0],self.enrollment,unit_state=state).can_access)
        with patch('modulearn.learning.services.access_rules.timezone.now',return_value=now):
            self.assertTrue(evaluate_unit_access(unit,self.enrollment).can_access)
        with patch('modulearn.learning.services.access_rules.timezone.now',return_value=unit.closes_at):
            self.assertFalse(evaluate_unit_access(unit,self.enrollment).can_access)

    def test_unit_roundtrip_duplicate_titles_internal_rules_and_practice(self):
        source=self.units[0]; source.opens_at=timezone.now(); source.save()
        a,b=self.modules[:2]
        b.title=a.title; b.is_graded=False; b.is_locked=True
        b.unlock_rule={'conditions':[{'type':'module_completed','target_id':a.id}]}; b.save()
        data=export_unit(source)
        unit,warnings=import_unit(self.course,data)
        self.assertNotEqual(unit.id,source.id)
        self.assertEqual(unit.opens_at,source.opens_at)
        imported=list(unit.modules.all())
        self.assertEqual(len(imported),4)
        self.assertEqual(imported[0].title,imported[1].title)
        self.assertFalse(imported[1].is_graded)
        self.assertEqual(imported[1].unlock_rule['conditions'][0]['target_id'],imported[0].id)
        self.assertEqual(ModuleProgress.objects.filter(enrollment=self.enrollment,module__unit=unit).count(),4)
        self.assertEqual(warnings,[])

    def test_external_prerequisite_is_not_silently_unlocked(self):
        self.modules[0].is_locked=True
        self.modules[0].unlock_rule={'conditions':[{'type':'module_completed','target_id':self.modules[4].id}]}
        self.modules[0].save()
        unit,warnings=import_unit(self.course,export_unit(self.units[0]))
        self.assertTrue(warnings)
        first=unit.modules.first()
        self.assertTrue(first.is_locked)
        self.assertFalse(evaluate_module_access(first,self.enrollment).can_access)

    def test_invalid_import_rolls_back(self):
        data=export_unit(self.units[0]); data['unit']['modules'][1]['ref']=data['unit']['modules'][0]['ref']
        before=Unit.objects.count()
        with self.assertRaises(ValueError): import_unit(self.course,data)
        self.assertEqual(Unit.objects.count(),before)

    def test_configuration_and_grading_templates_render(self):
        self.client.force_login(self.teacher)
        for name in ['course_configuration','grading']:
            response=self.client.get(reverse(f'courses:{name}',args=[self.instance.id]))
            self.assertEqual(response.status_code,200)
        self.assertContains(response,'Live grade preview')

    def test_bulk_recalculation_query_count_is_bounded(self):
        for i in range(12):
            user=User.objects.create_user(username=f'batch-{i}')
            Enrollment.objects.create(student=user,course_instance=self.instance)
        with self.assertNumQueries(5):
            refresh_session_grades(self.instance)

    def test_schedule_and_grade_toggle_save_and_invalid_schedule_rolls_back(self):
        self.client.force_login(self.teacher)
        fields = []
        for unit in self.units:
            fields.append([f'unit_{unit.id}_visible','1'])
        for module in self.modules:
            fields.extend([[f'module_{module.id}_visible','1'],[f'module_{module.id}_is_graded','0']])
        fields.extend([[f'unit_{self.units[0].id}_opens_at','2030-01-01T10:00'],[f'unit_{self.units[0].id}_closes_at','2030-01-02T10:00']])
        url=reverse('courses:course_configuration',args=[self.instance.id])
        self.assertEqual(self.client.post(url,{'action':'update_structure','structure_controls':json.dumps(fields)}).status_code,302)
        self.units[0].refresh_from_db()
        self.assertEqual(self.units[0].opens_at.year,2030)
        self.assertEqual(Module.objects.filter(unit__course=self.course,is_graded=True).count(),0)
        self.enrollment.course_progress.refresh_from_db()
        self.assertEqual(self.enrollment.course_progress.total_modules,0)
        self.assertEqual(self.enrollment.course_progress.practice_total,8)
        fields[-1][1]='2029-01-01T00:00'
        self.client.post(url,{'action':'update_structure','structure_controls':json.dumps(fields)})
        self.units[0].refresh_from_db()
        self.assertEqual(self.units[0].closes_at.year,2030)

    def test_form_and_file_roundtrip(self):
        import tempfile
        from django.core.files.base import ContentFile
        from courses.models import ModuleForm, ModuleFormQuestion
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            file=self.modules[0];file.module_type='file';file.content_file.save('notes.txt',ContentFile(b'unit notes'));file.save()
            form=self.modules[1];form.module_type='form';form.save()
            definition=ModuleForm.objects.create(module=form,instructions='Read carefully')
            ModuleFormQuestion.objects.create(form=definition,prompt='What did you learn?',question_type='short_answer')
            unit,_=import_unit(self.course,export_unit(self.units[0]))
            copies=list(unit.modules.all())
            self.assertNotEqual(copies[0].content_file.name,file.content_file.name)
            with copies[0].content_file.open('rb') as uploaded:self.assertEqual(uploaded.read(),b'unit notes')
            self.assertEqual(copies[1].form.instructions,'Read carefully')
            self.assertEqual(copies[1].form.questions.get().prompt,'What did you learn?')

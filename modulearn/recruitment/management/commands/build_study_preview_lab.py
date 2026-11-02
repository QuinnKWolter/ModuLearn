"""Create a reusable, recruitment-disabled three-condition routing rehearsal."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.urls import reverse

from courses.models import Module, ModuleForm, ModuleFormQuestion, ModuleBranchRule, Unit
from recruitment.models import Study
from recruitment.services.studies import create_study_for_instructor


class Command(BaseCommand):
    help = 'Create a draft study-flow lab. No provider URLs, real recruitment, or participant data are modified.'

    def add_arguments(self, parser):
        parser.add_argument('--teacher', default='RITEL_DEMO_Teacher')
        parser.add_argument('--title', default='Remediation Study — Flow Rehearsal')

    @transaction.atomic
    def handle(self, *args, **options):
        teacher = get_user_model().objects.filter(username=options['teacher'], is_instructor=True).first()
        if not teacher:
            raise CommandError('Create the instructor account first; this command does not alter accounts or passwords.')
        existing = Study.objects.filter(title=options['title'], instructors=teacher, preview_of__isnull=True).first()
        if existing:
            self.stdout.write('Existing lab retained: ' + reverse('recruitment:studio', args=[existing.pk]))
            return
        study = create_study_for_instructor(teacher, title=options['title'],
            description='Routing rehearsal only. Sample forms substitute for unpublished Cupcake/WEAT activities. Not the final experimental protocol.',
            condition_labels='practice,similar,matched')
        course = study.course_instance.course
        course.units.all().delete()

        def section(title, order, seconds=0):
            return Unit.objects.create(course=course, title=title, order=order, time_limit_seconds=seconds)

        def form(unit, title, instructions, order=10, *, answer=False):
            module = Module.objects.create(unit=unit, title=title, order=order, module_type='form',
                allow_resubmission=True, content_data={'rehearsal_only': True})
            authored = ModuleForm.objects.create(module=module, instructions=instructions, allow_resubmission=True,
                submit_button_label='Continue')
            ModuleFormQuestion.objects.create(form=authored,
                prompt='Your response' if answer else 'Ready to continue?',
                question_type='long_answer' if answer else 'single_choice',
                options=[] if answer else ['Continue'], required=True)
            return module

        before = section('Consent & Baseline', 10)
        form(before, 'Consent — Rehearsal', '**Preview only**\nThis is not approved consent text. Replace it with the study consent and eligibility information.')
        form(before, 'Baseline Measures — Placeholder', 'Insert the approved confidence, interest, experience, and pretest items.', 20, answer=True)
        learning = section('Learning Session', 20)
        remediation = section('Condition Remediation', 30)
        question_specs = [
            ('Q01 · Update a Score', 'Set `score` to 10, add 5, then add 3. Print `score`.',
             'score = 10\nscore = score + 5\nscore = score + 3\nprint(score)',
             'The first update makes 15; the next makes 18. Each assignment uses the current value.',
             'Start `x` at 2, add 1, then add 4. Print `x`.'),
            ('Q09 · Compare a Sum', 'Set `x` to 12 and `y` to 5. If their sum is greater than 15, set `result` to 1; otherwise 0. Print `result`.',
             'x = 12\ny = 5\nif x + y > 15:\n    result = 1\nelse:\n    result = 0\nprint(result)',
             'The sum is 17. Since 17 > 15, the first branch assigns 1.',
             'Set `a` to 3 and `b` to 4. Print 1 if their sum is greater than 5, otherwise 0.'),
        ]
        for index, (title, prompt, solution, explanation, similar) in enumerate(question_specs):
            original = form(learning, title, prompt + '\n\n**Rehearsal:** This form does not execute or grade Python. Branch outcomes are exercised by the automated preview tests.', (index+1)*10, answer=True)
            for label in ['practice', 'similar', 'matched']:
                instructions = similar if label == 'practice' else (
                    f'```python\n{solution}\n```\n{explanation}' if label == 'matched' else
                    f'**Similar example**\n{similar}\nStudy the same operations with different starting values. Replace this placeholder with the selected WEAT example.')
                target = form(remediation, f'{title} · {label}', instructions, (index+1)*10, answer=label=='practice')
                target.is_locked = True
                target.save(update_fields=['is_locked'])
                ModuleBranchRule.objects.create(course=course, source_module=original, target_module=target,
                    condition_type='failure', required_study_condition=label)
        after = section('Post-session Questionnaire', 40)
        form(after, 'Post-session Measures — Placeholder', 'Insert the approved distraction, interest, confidence, judgments of learning, expected test score, and confidence-in-estimate items.', answer=True)
        final = section('Final Test — Timer Demonstration', 50, 60)
        final_module = form(final, 'Transfer Test — Placeholder', '**Rehearsal timer: 60 seconds.**\nReplace these two questions and this duration with the approved test and rubric.', answer=True)
        ModuleFormQuestion.objects.create(form=final_module.form, prompt='Second transfer response', question_type='long_answer', order=20)
        final_module.content_data = {'rehearsal_only': True, 'study_shuffle_questions': True}
        final_module.save(update_fields=['content_data'])
        ending = section('Debrief', 60)
        form(ending, 'Debrief — Rehearsal', 'This rehearsal is complete. No recruitment credit will be issued.')
        study.notes = ('REHEARSAL ONLY. Q01 and Q09 are illustrative, not the selected final eight. '
            'Final activity URLs, pairings, consent, indices.docx, rubric.docx and section durations remain outstanding. '
            'Q04 expected Python output must be 15.0, not 15. '
            'Review whether a second incorrect original submission repeats remediation; current flow does so. '
            'Practice remediation returns after one scored submission; examples return after provider completion.')
        study.save(update_fields=['notes'])
        study.recruitment_sources.update(is_active=False, prolific_completion_code_complete='',
            prolific_completion_code_screened_out='', prolific_completion_code_attention_failed='')
        self.stdout.write(self.style.SUCCESS('Rehearsal ready: ' + reverse('recruitment:studio', args=[study.pk])))

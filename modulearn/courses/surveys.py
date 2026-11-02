"""Paged native surveys using the existing form, answer and activity history tables."""
import copy
import secrets

from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from courses.models import ModuleProgress, ModuleFormSubmission, ModuleFormAnswer
from modulearn.learning.services.progress import apply_progress_snapshot, log_module_progress_event


def new_draft(schema):
    order = [p['id'] for p in schema['pages']]
    rng = secrets.SystemRandom()
    for group in schema.get('page_shuffle_groups', []):
        positions = [i for i, key in enumerate(order) if key in group]
        shuffled = [order[i] for i in positions]
        rng.shuffle(shuffled)
        for i, key in zip(positions, shuffled):
            order[i] = key
    rows = {}
    for page in schema['pages']:
        keys = [row['key'] for row in page['rows']]
        if page.get('shuffle_rows'):
            rng.shuffle(keys)
        rows[page['id']] = keys
    return {'order': order, 'rows': rows, 'index': 0, 'answers': {},
            'token': secrets.token_hex(16), 'started_at': timezone.now().isoformat()}


@transaction.atomic
def handle_survey(request, instance, module, progress, is_instructor):
    # Serialize page transitions and final submissions, including retries in another tab.
    progress = ModuleProgress.objects.select_for_update().get(pk=progress.pk)
    schema = module.content_data['survey']
    state = copy.deepcopy(progress.state_data or {})
    draft = state.get('survey_draft') or new_draft(schema)
    pages = {p['id']: p for p in schema['pages']}
    page = pages[draft['order'][draft['index']]]
    can_back = draft['index'] > 0 and schema['pages'][draft['index']].get('back', True)
    questions = {q.order: q for q in module.form.questions.all()}
    error = ''
    if request.method == 'POST' and not draft.get('finished'):
        if request.POST.get('page_token') != draft['token']:
            error = 'This page has already changed. Review the current page before continuing.'
        else:
            back = request.POST.get('action') == 'back'
            answers = {}
            for row in page['rows']:
                options = {o['id']: o for o in row['options']}
                selected = list(dict.fromkeys(request.POST.getlist(row['key'])))
                if any(value not in options for value in selected) or (not row['multiple'] and len(selected) > 1):
                    error = 'Please select a valid response.'
                    continue
                question = questions[row['question_order']]
                if not back and question.required and not selected:
                    error = 'Please answer every item on this page.'
                text = {value: request.POST.get(row['key'] + '_text_' + value, '').strip()[:4000]
                        for value in selected if options[value].get('text_entry')}
                answers[row['key']] = {'codes': selected, 'labels': [options[v]['label'] for v in selected],
                    'text': text, 'tag': page['tag'], 'question_id': page['id'],
                    'saved_at': timezone.now().isoformat()}
            if back and not can_back:
                error = 'You cannot return to the previous section.'
            draft['answers'].update(answers)
            if not error:
                decline = schema.get('decline') or {}
                declined = decline.get('value') in draft['answers'].get(decline.get('key'), {}).get('codes', [])
                final = not back and (declined or draft['index'] == len(draft['order']) - 1)
                log_module_progress_event(progress, event_type='study_input', source='native_survey',
                    payload={'action': 'back' if back else 'page_saved', 'page': page['id'],
                             'answers': answers, 'page_order': draft['order'], 'row_order': draft['rows'][page['id']]})
                if final:
                    if declined:
                        draft['answers'] = {decline['key']: draft['answers'][decline['key']]}
                    submission = ModuleFormSubmission.objects.create(form=module.form,
                        enrollment=progress.enrollment, user=request.user, is_complete=not declined)
                    records = []
                    for source_page in schema['pages']:
                        for row in source_page['rows']:
                            answer = draft['answers'].get(row['key'])
                            if answer is not None:
                                records.append(ModuleFormAnswer(submission=submission,
                                    question=questions[row['question_order']], value={'answer': answer['labels'], **answer},
                                    text_value='; '.join(answer['labels']) +
                                        ((' — ' + '; '.join(answer['text'].values())) if answer['text'] else '')))
                    ModuleFormAnswer.objects.bulk_create(records)
                    draft.update(finished=True, declined=declined, submission_id=submission.pk,
                                 finished_at=timezone.now().isoformat())
                    state['survey_draft'] = draft
                    if not declined:
                        apply_progress_snapshot(progress, source='native_survey', progress=1, is_complete=True,
                            payload=state, event_type='completion', submission=True)
                    else:
                        log_module_progress_event(progress, event_type='study_input', source='native_survey',
                            payload={'action': 'consent_declined', 'submission_id': submission.pk})
                    progress.attempts += 1
                else:
                    draft['index'] += -1 if back else 1
                draft['token'] = secrets.token_hex(16)
                state['survey_draft'] = draft
                progress.state_data = state
                progress.save(update_fields=['state_data', 'attempts', 'last_accessed'])
                return redirect(request.path)
    state['survey_draft'] = draft
    progress.state_data = state
    progress.save(update_fields=['state_data'])
    display = copy.deepcopy(page)
    rows = {r['key']: r for r in display['rows']}
    display['rows'] = [rows[key] for key in draft['rows'][page['id']]]
    for row in display['rows']:
        question = questions[row['question_order']]
        row['prompt'] = question.prompt
        row['required'] = question.required
        answer = draft['answers'].get(row['key'], {})
        for position, option in enumerate(row['options'], 1):
            option['checked'] = option['id'] in answer.get('codes', [])
            option['text'] = answer.get('text', {}).get(option['id'], '')
            option['accessible_label'] = option['label'] or str(position)
    return render(request, 'courses/module_survey.html', {
        'module': module, 'course_instance': instance, 'page': display, 'draft': draft,
        'can_back': can_back, 'error': error, 'end_text': schema['end_text'],
        'number': draft['index'] + 1, 'total': len(draft['order']),
        'percent': round(100 * draft['index'] / len(draft['order'])),
        'is_last': draft['index'] == len(draft['order']) - 1,
        'participant_mode': getattr(request.user, 'is_anonymous_participant', False),
        'is_instructor': is_instructor,
    })

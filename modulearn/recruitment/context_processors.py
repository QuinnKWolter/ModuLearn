from django.urls import reverse


def study_player(request):
    if not getattr(request.user, 'is_authenticated', False):
        return {}
    from recruitment.services.participants import get_current_participant_session
    session = get_current_participant_session(request.user)
    if not session or not session.recruitment_source.study_id:
        return {}
    study = session.recruitment_source.study
    if not study.guided_flow:
        return {}
    context = {'study_shell': True, 'study_preview': bool(study.preview_of_id)}
    if session.is_finished:
        return context
    context['study_player'] = {
        'status_url': reverse('recruitment:flow_status', args=[session.uuid]),
        'preview': bool(study.preview_of_id),
        'condition': session.condition if study.preview_of_id else '',
        'input_url': reverse('recruitment:input_summary', args=[session.uuid]),
        'continue_url': reverse('recruitment:continue_resource', args=[session.uuid]),
        'simulate_url': reverse('recruitment:simulate', args=[session.uuid]) if study.preview_of_id else '',
    }
    return context

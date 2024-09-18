from django.shortcuts import render, get_object_or_404
from courses.models import Module

def module_render(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    # Render the module based on its type
    if module.module_type == 'quiz':
        template_name = 'content/quiz.html'
    elif module.module_type == 'coding':
        template_name = 'content/coding.html'
    elif module.module_type == 'simulation':
        template_name = 'content/simulation.html'
    else:
        template_name = 'content/default.html'
    return render(request, template_name, {'module': module})

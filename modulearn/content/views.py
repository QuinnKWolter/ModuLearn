from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from courses.models import Module, Course, Enrollment, ModuleProgress

@login_required
def module_render(request, module_id):
    """
    Renders the smart content for a specific module.
    """
    module = get_object_or_404(Module, id=module_id)
    course = module.course

    # Check if the user is enrolled
    if not Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.error(request, 'You must be enrolled in the course to access this module.')
        return redirect('courses:course_detail', course_id=course.id)

    # Retrieve or create module progress
    enrollment = Enrollment.objects.get(student=request.user, course=course)
    module_progress, created = ModuleProgress.objects.get_or_create(
        enrollment=enrollment, module=module
    )

    if request.method == 'POST':
        # Process submitted data based on module type
        if module.module_type == 'quiz':
            # Process quiz submission
            # For example, calculate score and update progress
            user_answers = request.POST.dict()
            # Logic to calculate score goes here
            module_progress.is_complete = True
            module_progress.score = 100  # Placeholder for calculated score
            module_progress.save()
            messages.success(request, 'Quiz submitted successfully.')
            return redirect('dashboard:student_dashboard')
        elif module.module_type == 'coding':
            # Process coding challenge submission
            code = request.POST.get('code')
            # Logic to evaluate code goes here
            module_progress.is_complete = True
            module_progress.score = 100  # Placeholder for calculated score
            module_progress.save()
            messages.success(request, 'Code submitted successfully.')
            return redirect('dashboard:student_dashboard')
        elif module.module_type == 'simulation':
            # Process simulation interaction
            # Logic goes here
            pass

    return render(request, 'content/module_render.html', {'module': module})

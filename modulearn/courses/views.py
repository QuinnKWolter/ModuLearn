from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Course, Module, Enrollment, Unit
from django.contrib.auth import get_user_model
from django.http import JsonResponse
import json
from .utils import fetch_course_details, create_course_from_json
import logging
import traceback

User = get_user_model()

# Configure logging
logger = logging.getLogger(__name__)

def course_list(request):
    """
    Displays a list of all available courses.
    """
    courses = Course.objects.all()
    
    # Get LTI context data if available
    lti_data = {}
    if hasattr(request.user, 'lti_data') and request.user.lti_data:
        lti_data = {
            'name': request.user.lti_data.get('name'),
            'email': request.user.lti_data.get('email'),
            'roles': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/roles', []),
            'context': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/context', {}),
            'platform': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/tool_platform', {}),
            'resource_link': request.user.lti_data.get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}),
            'picture': request.user.lti_data.get('picture'),
        }
    
    return render(request, 'courses/course_list.html', {
        'courses': courses,
        'lti_data': lti_data
    })

@login_required
def course_detail(request, course_id):
    """
    Displays details of a specific course and handles enrollment.
    """
    course = get_object_or_404(Course, id=course_id)
    units = course.units.all()
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()

    # Determine if the user is an instructor for this course
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()

    if request.method == 'POST' and not enrolled and request.user.is_student:
        Enrollment.objects.create(student=request.user, course=course)
        messages.success(request, f'You have enrolled in {course.title}.')
        return redirect('courses:course_detail', course_id=course_id)

    return render(request, 'courses/course_detail.html', {
        'course': course,
        'units': units,
        'enrolled': enrolled,
        'is_instructor': is_instructor
    })

@login_required
def module_detail(request, course_id, unit_id, module_id):
    """
    Displays details of a specific module within a course.
    """
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    module = get_object_or_404(Module, id=module_id, unit=unit)
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()

    # Determine if the user is an instructor for this course
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()

    if not enrolled and not is_instructor:
        messages.error(request, 'You must be enrolled in the course to access modules.')
        return redirect('courses:course_detail', course_id=course_id)

    # Redirect to module render view if it's an external iframe
    if module.module_type == 'external_iframe':
        return redirect('courses:module_render', module_id=module.id)

    return render(request, 'courses/module_detail.html', {'module': module})

@login_required
def module_render(request, module_id):
    """
    Renders the smart content for a specific module.
    """
    module = get_object_or_404(Module, id=module_id)
    course = module.unit.course

    # Check if the user is enrolled or is an instructor
    enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    is_instructor = request.user.is_instructor and course.instructors.filter(id=request.user.id).exists()

    if not enrolled and not is_instructor:
        messages.error(request, 'You must be enrolled in the course to access this module.')
        return redirect('courses:course_detail', course_id=course.id)

    # Handle module types
    if module.module_type == 'external_iframe':
        template_name = 'courses/external_iframe.html'
    else:
        # Existing logic for other module types
        template_name = 'courses/module_render.html'

    return render(request, template_name, {'module': module})

@login_required
def unenroll(request, course_id):
    """
    Allows a user to unenroll from a course.
    """
    course = get_object_or_404(Course, id=course_id)
    enrollment = Enrollment.objects.filter(student=request.user, course=course).first()

    if enrollment:
        enrollment.delete()
        messages.success(request, f'You have unenrolled from {course.title}.')
    else:
        messages.error(request, 'You are not enrolled in this course.')

    return redirect('courses:course_detail', course_id=course_id)

@login_required
def create_course(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            if 'course_data' in data:
                # Handle raw JSON input
                create_course_from_json(data['course_data'], request.user)
                return JsonResponse({'success': True})
            elif 'course_id' in data:
                # Handle Course ID input
                fetch_course_details(data['course_id'])
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid input'})
        
        except Exception as e:
            # Log the exception with a stack trace
            logger.error("Error creating course: %s", str(e))
            logger.error(traceback.format_exc())
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

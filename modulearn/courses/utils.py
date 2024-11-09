import requests
import logging
from .models import Course, Unit, Module
from django.contrib.auth import get_user_model

# Configure logging
logger = logging.getLogger(__name__)

User = get_user_model()

def fetch_course_details(course_id):
    logger.debug(f"Starting fetch_course_details for course_id: {course_id}")
    
    # Fetch course data from the external API
    url = f"http://adapt2.sis.pitt.edu/next.course-authoring/api/courses/{course_id}/export"
    logger.debug(f"Fetching course data from URL: {url}")
    
    try:
        response = requests.get(url)
        logger.debug(f"Received response with status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        raise Exception(f"Request failed: {e}")
    
    if response.status_code != 200:
        # Log the response content for debugging
        error_message = f"Failed to fetch course details: {response.status_code}, Response: {response.text}"
        logger.error(error_message)
        raise Exception(error_message)
    
    try:
        course_data = response.json()
        logger.debug(f"Course data received: {course_data}")
    except ValueError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        raise Exception(f"Failed to parse JSON response: {e}")
    
    # Create the Course object
    course, created = Course.objects.get_or_create(
        external_id=course_data['id'],
        defaults={
            'title': course_data['name'],
            'description': course_data['description']
        }
    )
    logger.debug(f"Course {'created' if created else 'retrieved'}: {course}")
    
    # Create Unit and Module objects
    for unit_data in course_data.get('units', []):
        unit, created = Unit.objects.get_or_create(
            course=course,
            title=unit_data['name'],
            defaults={'description': unit_data['description']}
        )
        logger.debug(f"Unit {'created' if created else 'retrieved'}: {unit}")
        
        for resource_id, activities in unit_data.get('activities', {}).items():
            for activity in activities:
                module, created = Module.objects.get_or_create(
                    unit=unit,
                    title=activity['name'],
                    defaults={
                        'description': f"Provider: {activity['provider_id']}, Author: {activity['author_id']}",
                        'module_type': 'external_iframe',  # Assuming all are external iframes
                        'iframe_url': activity['url']
                    }
                )
                logger.debug(f"Module {'created' if created else 'retrieved'}: {module}")
    
    logger.debug(f"Finished processing course_id: {course_id}")
    return course

def create_course_from_json(course_data, current_user):
    logger.debug(f"Creating course from JSON data: {course_data}")
    
    # Use the 'id' from the JSON as the primary key
    course_id = course_data['id']
    
    # Create the Course object
    course, created = Course.objects.get_or_create(
        id=course_id,  # Use the JSON 'id' as the primary key
        defaults={
            'title': course_data['name'],
            'description': course_data['description'],
        }
    )
    logger.debug(f"Course {'created' if created else 'retrieved'}: {course}")
    
    # Add the current user as an instructor
    if current_user.is_instructor:
        course.instructors.add(current_user)
    
    # Add the instructor from the JSON data
    instructor_data = course_data.get('instructor', {})
    if instructor_data:
        instructor_email = instructor_data.get('email')
        if instructor_email:
            instructor_user, created = User.objects.get_or_create(
                email=instructor_email,
                defaults={'username': instructor_email.split('@')[0], 'is_instructor': True}
            )
            course.instructors.add(instructor_user)
    
    # Create Unit and Module objects
    for unit_data in course_data.get('units', []):
        unit, created = Unit.objects.get_or_create(
            course=course,
            title=unit_data['name'],
            defaults={'description': unit_data['description']}
        )
        logger.debug(f"Unit {'created' if created else 'retrieved'}: {unit}")
        
        for resource_id, activities in unit_data.get('activities', {}).items():
            for activity in activities:
                module, created = Module.objects.get_or_create(
                    unit=unit,
                    title=activity['name'],
                    defaults={
                        'description': f"Provider: {activity['provider_id']}, Author: {activity['author_id']}",
                        'module_type': 'external_iframe',  # Assuming all are external iframes
                        'iframe_url': activity['url']
                    }
                )
                logger.debug(f"Module {'created' if created else 'retrieved'}: {module}")
    
    logger.debug(f"Finished creating course from JSON data")
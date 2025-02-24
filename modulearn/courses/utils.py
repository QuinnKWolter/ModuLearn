import requests
import logging
from .models import Course, Unit, Module
from django.contrib.auth import get_user_model
import json
import traceback
import uuid
from oauthlib.oauth1 import Client
from oauthlib.oauth1.rfc5849 import signature

# Configure logging
logger = logging.getLogger(__name__)

User = get_user_model()

def fetch_course_details(course_id, user):
    logger.info(f"Starting fetch_course_details for course_id: {course_id}")
    
    # Get the authentication token
    token = get_course_auth_token(user)
    
    url = f"https://proxy.personalized-learning.org/next.course-authoring/api/courses/{course_id}/export"
    logger.info(f"Fetching course data from URL: {url}")
    
    headers = {
        'token': token
    }
    
    try:
        response = requests.get(url, headers=headers)
        logger.info(f"Received response with status code: {response.status_code}")
        logger.debug(f"Response content: {response.text[:500]}...")  # Log first 500 chars
        
        if response.status_code != 200:
            error_message = f"Failed to fetch course details: Status {response.status_code}, Response: {response.text}"
            logger.error(error_message)
            raise Exception(error_message)
        
        course_data = response.json()
        if not course_data:
            logger.error("Empty response from API")
            raise Exception("Empty response from API")
            
        logger.info("Successfully fetched course data")
        logger.debug(f"Course data structure: {list(course_data.keys())}")
        return course_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        raise Exception(f"Failed to connect to course API: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        logger.error(f"Raw response: {response.text[:500]}...")
        raise Exception(f"Invalid JSON response from API: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_course_details: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def create_course_from_json(course_data, current_user):
    logger.debug(f"Creating course from JSON data: {course_data}")
    
    # Use the 'id' from the JSON as the primary key
    course_id = course_data['id']
    
    # Create the Course object
    course, created = Course.objects.get_or_create(
        id=course_id,  # Use the JSON 'id' as the primary key
        defaults={
            'title': course_data.get('name', ''),
            'description': course_data.get('description', ''),
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
            defaults={'description': unit_data.get('description', '')}
        )
        logger.debug(f"Unit {'created' if created else 'retrieved'}: {unit}")
        
        for resource_id, activities in unit_data.get('activities', {}).items():
            for activity in activities:
                module, created = Module.objects.get_or_create(
                    unit=unit,
                    title=activity['name'],
                    defaults={
                        'description': f"Provider: {activity.get('provider_id', 'unknown')}, Author: {activity.get('author_id', 'unknown')}",
                        'content_url': activity.get('url', '')
                    }
                )
                logger.debug(f"Module {'created' if created else 'retrieved'}: {module}")
    
    logger.info(f"Successfully created/updated course: {course}")
    return course  # Make sure we return the course object

def send_grade_to_canvas(xml_payload, outcome_service_url, consumer_key, consumer_secret):
    """Helper function to send grades to Canvas via LTI 1.1"""
    
    client = Client(
        client_key=consumer_key,
        client_secret=consumer_secret,
    )
    
    # Generate OAuth1 signature
    oauth_params = client.get_oauth_params()
    oauth_params.append(('oauth_body_hash', signature.sign_plaintext(xml_payload, consumer_secret)))
    
    # Get authorization header
    auth_header = client.get_oauth_signature(
        outcome_service_url,
        http_method='POST',
        oauth_params=oauth_params
    )
    
    headers = {
        'Content-Type': 'application/xml',
        'Authorization': auth_header,
    }
    
    # Send the request
    return requests.post(
        outcome_service_url,
        data=xml_payload,
        headers=headers,
        verify=True
    )

def get_course_auth_token(user):
    """
    Generates an encrypted token for course authoring login.
    """
    if not user.is_authenticated:
        raise ValueError("User not authenticated")

    # Fetch user details
    user_email = user.email
    user_fullname = f"{user.first_name} {user.last_name}"

    # Generate or retrieve stored password
    if not user.course_authoring_password:
        user.course_authoring_password = str(uuid.uuid4())  # Generate a UUID password
        user.save()

    # Create payload
    payload = {
        "fullname": user_fullname,
        "email": user_email,
        "password": user.course_authoring_password,
    }

    print(f"Payload for token request: {payload}")

    # Make POST request to obtain the encrypted token
    try:
        response = requests.post(
            "https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login-token",
            json=payload
        )
        response.raise_for_status()
        print(f"Raw response content: {response.content}")

        # Extract token
        token = response.text.strip()
        print(f"Token received: {token}")
        return token
    except requests.exceptions.RequestException as e:
        print(f"Request exception occurred: {e}")
        raise
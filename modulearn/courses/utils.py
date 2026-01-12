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
        'Authorization': f'Bearer {token}'
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

    # If the course already existed, update mutable fields from JSON
    if not created:
        updated = False
        title = course_data.get('name', '')
        description = course_data.get('description', '')
        if title and course.title != title:
            course.title = title
            updated = True
        if description != course.description:
            course.description = description
            updated = True
        if updated:
            course.save()
    
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
    provider_protocols_map = course_data.get('provider_protocols', {}) or {}
    for unit_data in course_data.get('units', []):
        unit, created = Unit.objects.get_or_create(
            course=course,
            title=unit_data['name'],
            defaults={'description': unit_data.get('description', '')}
        )
        logger.debug(f"Unit {'created' if created else 'retrieved'}: {unit}")
        
        for resource_id, activities in unit_data.get('activities', {}).items():
            for activity in activities:
                provider_id = activity.get('provider_id', '') or ''
                supported_protocols = provider_protocols_map.get(provider_id, [])
                module, created = Module.objects.get_or_create(
                    unit=unit,
                    title=activity['name'],
                    defaults={
                        'description': f"Provider: {provider_id or 'unknown'}, Author: {activity.get('author_id', 'unknown')}",
                        'content_url': activity.get('url', ''),
                        'provider_id': provider_id,
                        'supported_protocols': supported_protocols,
                    }
                )
                # Update protocols/provider if module existed and differs
                updated = False
                if module.provider_id != provider_id:
                    module.provider_id = provider_id
                    updated = True
                if module.supported_protocols != supported_protocols:
                    module.supported_protocols = supported_protocols
                    updated = True
                if updated:
                    module.save()
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

def reset_course_authoring_password(user):
    """
    Resets the course-authoring password for a user by generating a new UUID.
    This is useful when there's a password mismatch with course-authoring.
    
    Returns:
        str: The new password UUID that needs to be set in course-authoring
    """
    new_password = str(uuid.uuid4())
    user.course_authoring_password = new_password
    user.save()
    logger.info(f"Reset course-authoring password for user {user.email}. New password: {new_password}")
    return new_password


def get_course_auth_token(user, retry_on_mismatch=False):
    """
    Generates an encrypted token for course authoring login.
    
    Args:
        user: The authenticated user
        retry_on_mismatch: If True and password mismatch occurs, reset password and retry once
    
    Raises:
        ValueError: If user is not authenticated
        requests.exceptions.HTTPError: If authentication fails with course-authoring
        Exception: For other unexpected errors
    """
    if not user.is_authenticated:
        raise ValueError("User not authenticated")

    # Fetch user details
    user_email = user.email
    user_fullname = f"{user.full_name or user.get_full_name() or user.username}"

    # Generate or retrieve stored password
    if not user.course_authoring_password:
        user.course_authoring_password = str(uuid.uuid4())  # Generate a UUID password
        user.save()
        logger.info(f"Generated new course-authoring password for user {user_email}: {user.course_authoring_password[:16]}...")
    
    password = user.course_authoring_password

    # Create payload
    payload = {
        "fullname": user_fullname,
        "email": user_email,
        "password": password,
    }

    # Comprehensive logging of request
    logger.info("=" * 80)
    logger.info(f"COURSE-AUTHORING AUTH REQUEST for user: {user_email}")
    logger.info(f"Request URL: https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login-token")
    logger.info(f"Request Method: POST")
    logger.info(f"Request Headers: Content-Type: application/json")
    logger.info(f"Request Payload (full): {json.dumps(payload, indent=2)}")
    logger.info(f"Password (first 16 chars): {password[:16]}...")
    logger.info(f"Password stored in DB: Yes")
    logger.info(f"Full Name: {user_fullname}")
    logger.info(f"Email: {user_email}")
    logger.info("-" * 80)

    # Make POST request to obtain the encrypted token
    try:
        response = requests.post(
            "https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login-token",
            json=payload,
            timeout=10
        )
        
        # Comprehensive logging of response
        logger.info(f"Response Status Code: {response.status_code}")
        logger.info(f"Response Headers: {dict(response.headers)}")
        logger.info(f"Response Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        logger.info(f"Response Content Length: {len(response.content)} bytes")
        
        # Log response body (be careful with sensitive data)
        try:
            response_json = response.json()
            logger.info(f"Response Body (JSON): {json.dumps(response_json, indent=2)}")
        except (ValueError, json.JSONDecodeError):
            # Not JSON, log as text (might be encrypted token)
            response_text = response.text
            if len(response_text) > 200:
                logger.info(f"Response Body (Text, first 200 chars): {response_text[:200]}...")
            else:
                logger.info(f"Response Body (Text): {response_text}")
        
        response.raise_for_status()

        # Extract token
        token = response.text.strip()
        logger.info(f"Successfully obtained x-login-token for user {user_email}")
        logger.info(f"Token length: {len(token)} characters")
        logger.info(f"Token (first 50 chars): {token[:50]}...")
        logger.info("=" * 80)
        return token
        
    except requests.exceptions.HTTPError as e:
        # Comprehensive error logging
        logger.error("=" * 80)
        logger.error(f"COURSE-AUTHORING AUTH ERROR for user: {user_email}")
        logger.error(f"Error Type: HTTPError")
        logger.error(f"Response Status Code: {e.response.status_code if e.response else 'N/A'}")
        
        if e.response:
            logger.error(f"Response Headers: {dict(e.response.headers)}")
            logger.error(f"Response Content-Type: {e.response.headers.get('Content-Type', 'N/A')}")
            
            # Try to parse error response
            try:
                error_data = e.response.json()
                logger.error(f"Response Body (JSON): {json.dumps(error_data, indent=2)}")
                error_message = error_data.get('message', 'Unknown error')
            except (ValueError, json.JSONDecodeError):
                error_text = e.response.text
                logger.error(f"Response Body (Text): {error_text}")
                error_message = error_text or "Unknown error"
        else:
            error_message = str(e)
            logger.error(f"Error Message: {error_message}")
        
        logger.error(f"Request that failed:")
        logger.error(f"  URL: https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login-token")
        logger.error(f"  Method: POST")
        logger.error(f"  Payload: {json.dumps(payload, indent=2)}")
        logger.error("=" * 80)
        
        # Handle specific 422 error (password mismatch or invalid credentials)
        if e.response and e.response.status_code == 422:
            logger.warning(
                f"Authentication failed for user {user_email}: {error_message}. "
                f"This usually means the user exists in course-authoring with a different password. "
                f"Password used: {password[:16]}..."
            )
            
            # If retry_on_mismatch is enabled, reset password and try once more
            if retry_on_mismatch:
                logger.info(f"Retrying with new password for user {user_email}")
                new_password = reset_course_authoring_password(user)
                payload['password'] = new_password
                
                # Log retry attempt
                logger.info("=" * 80)
                logger.info(f"RETRY ATTEMPT for user: {user_email}")
                logger.info(f"New Password (first 16 chars): {new_password[:16]}...")
                logger.info(f"Retry Payload: {json.dumps(payload, indent=2)}")
                logger.info("-" * 80)
                
                try:
                    response = requests.post(
                        "https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login-token",
                        json=payload,
                        timeout=10
                    )
                    
                    # Log retry response
                    logger.info(f"Retry Response Status: {response.status_code}")
                    logger.info(f"Retry Response Headers: {dict(response.headers)}")
                    try:
                        retry_json = response.json()
                        logger.info(f"Retry Response Body: {json.dumps(retry_json, indent=2)}")
                    except:
                        logger.info(f"Retry Response Body (Text): {response.text[:200]}...")
                    
                    response.raise_for_status()
                    token = response.text.strip()
                    logger.info(f"Successfully obtained x-login-token after password reset for user {user_email}")
                    logger.info("=" * 80)
                    return token
                except requests.exceptions.HTTPError as retry_error:
                    # Still failed after reset - user definitely exists with different password
                    logger.error(f"Authentication still failed after password reset for user {user_email}")
                    logger.error(f"Retry Error Status: {retry_error.response.status_code if retry_error.response else 'N/A'}")
                    if retry_error.response:
                        try:
                            retry_error_data = retry_error.response.json()
                            logger.error(f"Retry Error Body: {json.dumps(retry_error_data, indent=2)}")
                        except:
                            logger.error(f"Retry Error Body (Text): {retry_error.response.text}")
                    logger.error("=" * 80)
                    raise requests.exceptions.HTTPError(
                        f"Password mismatch detected. The user exists in course-authoring with a different password. "
                        f"A new password has been generated: {new_password}. "
                        f"Please contact the course-authoring administrator to set this password for your account, "
                        f"or use the 'Reset Course-Authoring Password' option in your profile.",
                        response=retry_error.response if hasattr(retry_error, 'response') else e.response
                    )
            
            # Create a more descriptive error with actionable instructions
            current_password = user.course_authoring_password
            raise requests.exceptions.HTTPError(
                f"PASSWORD_MISMATCH: The user account exists in course-authoring but the password doesn't match. "
                f"ModuLearn's stored password: {current_password}. "
                f"To fix this, you can:\n"
                f"1. Use the 'Reset Course-Authoring Password' option (generates a new password you can share with admin)\n"
                f"2. Contact support to sync the password in course-authoring\n"
                f"3. If you have course-authoring access, reset your password there to match: {current_password}",
                response=e.response
            )
        else:
            # Other HTTP errors
            logger.error(
                f"HTTP error {e.response.status_code if e.response else 'unknown'} "
                f"when requesting x-login-token for user {user_email}: {e}"
            )
            logger.error("=" * 80)
            raise
            
    except requests.exceptions.RequestException as e:
        logger.error("=" * 80)
        logger.error(f"REQUEST EXCEPTION when getting x-login-token for user {user_email}")
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error(f"Request URL: https://proxy.personalized-learning.org/next.course-authoring/api/auth/x-login-token")
        logger.error(f"Request Payload: {json.dumps(payload, indent=2)}")
        logger.error("=" * 80)
        raise Exception(f"Failed to connect to course-authoring API: {str(e)}")
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"UNEXPECTED ERROR getting x-login-token for user {user_email}")
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error(f"Traceback:")
        logger.error(traceback.format_exc())
        logger.error("=" * 80)
        raise

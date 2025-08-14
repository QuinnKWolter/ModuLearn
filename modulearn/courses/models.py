from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
import json
import requests
from oauthlib.oauth1 import Client
from oauthlib.oauth1.rfc5849 import signature, parameters
import uuid
from django.conf import settings
import logging
import jwt
import time
import hashlib
import base64
import hmac
from urllib.parse import quote, urlencode


User = get_user_model()
logger = logging.getLogger(__name__)

class Course(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructors = models.ManyToManyField(User, related_name='courses_taught', limit_choices_to={'is_instructor': True}, blank=True)

    def __str__(self):
        return self.title

    def total_modules(self):
        """Return the total number of modules in the course."""
        return Module.objects.filter(unit__course=self).count()

class CourseInstance(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='instances', null=True, blank=True)
    group_name = models.CharField(max_length=255, blank=True, help_text="Custom identifier for the student group")
    instructors = models.ManyToManyField(User, related_name='course_instances_taught', limit_choices_to={'is_instructor': True}, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    canvas_course_id = models.CharField(max_length=255, null=True, blank=True)
    canvas_assignment_id = models.CharField(max_length=255, null=True, blank=True)
    lis_outcome_service_url = models.URLField(null=True, blank=True)

    class Meta:
        unique_together = ('course', 'group_name')

    def __str__(self):
        return f"{self.course.title} - {self.group_name}"

    def duplicate(self, new_group_name):
        """Create a new instance of this course with a different group name"""
        if CourseInstance.objects.filter(course=self.course, group_name=new_group_name).exists():
            raise ValueError("A course instance with this group name already exists")
        
        new_instance = CourseInstance.objects.create(
            course=self.course,
            group_name=new_group_name
        )
        
        # Copy instructors
        for instructor in self.instructors.all():
            new_instance.instructors.add(instructor)
        
        return new_instance

class Unit(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='units')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.course.title} - {self.title}"

class Module(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='modules', null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    content_data = models.JSONField(blank=True, null=True)
    content_url = models.URLField(blank=True, null=True)
    keywords = models.CharField(max_length=500, blank=True)
    platform_name = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=255, blank=True)
    provider_id = models.CharField(max_length=255, blank=True)
    supported_protocols = models.JSONField(blank=True, null=True)
    resource_link_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="LTI resource link ID"
    )

    def __str__(self):
        course_title = self.unit.course.title if self.unit and self.unit.course else "No Course"
        unit_title = self.unit.title if self.unit else "No Unit"
        return f"{course_title} - {unit_title} - {self.title}"

    @property
    def course(self):
        return self.unit.course if self.unit else None

    def get_student_progress(self, user):
        try:
            return ModuleProgress.objects.get(
                enrollment__student=user,
                enrollment__course=self.unit.course,
                module=self
            )
        except ModuleProgress.DoesNotExist:
            return None

    class Meta:
        indexes = [
            models.Index(fields=['resource_link_id']),
        ]

    def select_launch_protocol(self, preferred_order=None):
        """Return the best-supported protocol for this module.

        Priority default: ['splice', 'lti', 'pitt']
        Returns the protocol string or None if none are available.
        """
        if preferred_order is None:
            preferred_order = ['splice', 'lti', 'pitt']

        available = self.supported_protocols or []
        for protocol in preferred_order:
            if protocol in available:
                return protocol
        return None

class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course_instance = models.ForeignKey(CourseInstance, on_delete=models.CASCADE, related_name='enrollments')
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'course_instance')

    def __str__(self):
        return f"{self.student.username} - {self.course_instance}"

class ModuleProgress(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='module_progress', null=True, blank=True)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Progress tracking
    progress = models.FloatField(default=0.0, help_text='Progress between 0 and 1')
    is_complete = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    success = models.BooleanField(default=False)
    
    # Attempt tracking
    attempts = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    
    # Timing tracking
    first_accessed = models.DateTimeField(default=timezone.now)
    last_accessed = models.DateTimeField(auto_now=True)
    total_duration = models.DurationField(default=timedelta())
    
    # State data
    state_data = models.JSONField(blank=True, null=True)
    last_response = models.TextField(blank=True)
    
    # LTI fields
    lis_result_sourcedid = models.CharField(max_length=255, null=True, blank=True)
    lis_outcome_service_url = models.URLField(null=True, blank=True)
    
    class Meta:
        unique_together = [('user', 'module', 'enrollment')]

    def __str__(self):
        return f"{self.user.username}'s progress in {self.module.title}"

    @classmethod
    def get_or_create_progress(cls, user, module, course_instance):
        """Get or create progress record based on user role in this specific course instance"""
        # First, check if user is instructor for this course instance
        is_instructor = course_instance.instructors.filter(id=user.id).exists()
        
        if is_instructor:
            return cls.objects.get_or_create(
                user=user,
                module=module,
                defaults={
                    'enrollment': None,
                    'progress': 1.0,
                    'is_complete': True
                }
            )
        else:
            try:
                enrollment = Enrollment.objects.get(student=user, course_instance=course_instance)
            except Enrollment.DoesNotExist:
                enrollment = Enrollment.objects.create(student=user, course_instance=course_instance)
            
            return cls.objects.get_or_create(
                user=user,
                module=module,
                enrollment=enrollment
            )

    def update_progress(self, new_progress):
        """Update module progress and potentially submit course grade"""
        self.progress = new_progress
        self.save()

        print("Updating progress:", self.progress)
        
        # If module is completed, update course progress
        if self.progress >= 1.0:
            print("Module is completed, updating course progress")
            course_progress = self.enrollment.course_progress
            course_progress.recalculate_progress()
            # Submit updated grade to Canvas
            course_progress.submit_grade_to_canvas()

    def update_from_activity_attempt(self, data):
        """Update progress based on activity attempt data"""
        print("Updating from activity attempt:", data)
        if not isinstance(data, dict) or 'data' not in data or not data['data']:
            print("Invalid data format")
            return
        
        activity_data = data['data'][0]  # Get the first activity
        print(f"Processing activity data: {activity_data}")
        
        self.attempts += 1
        self.last_response = json.dumps(activity_data)
        
        # Update fields from the activity data
        try:
            if 'score' in activity_data:
                self.score = float(activity_data['score'])
                print(f"Updated score: {self.score}")
            if 'progress' in activity_data:
                self.progress = float(activity_data['progress']) / 100.0
                print(f"Updated progress: {self.progress}")
            if 'success' in activity_data:
                self.success = bool(activity_data['success'])
                print(f"Updated success: {self.success}")
            if 'completion' in activity_data:
                self.is_complete = bool(activity_data['completion'])
                print(f"Updated completion: {self.is_complete}")
            if 'response' in activity_data:
                self.state_data = activity_data['response']
            
            self.save()
            print("Saved ModuleProgress updates")
            
            # Update course progress if there's an enrollment
            if self.enrollment and hasattr(self.enrollment, 'course_progress'):
                print("Updating course progress")
                self.enrollment.course_progress.update_progress()
                print("Course progress updated")
            
        except Exception as e:
            logger.error(f"Error updating module progress: {str(e)}")
            raise

    def submit_grade_to_canvas(self):
        """Submit grade to Canvas via LTI 1.1 or 1.3"""
        print("Submitting grade to Canvas MODULE PROGRESS!")
        if not (self.lis_result_sourcedid and self.lis_outcome_service_url):
            logger.warning("Missing LTI grade passback credentials")
            return False
        
        try:
            # Get LTI 1.1 credentials
            consumer_key = settings.LTI_11_CONSUMER_KEY
            consumer_secret = settings.LTI_11_CONSUMER_SECRET
            print(f"Using consumer key: {consumer_key}")
            
            # Convert score to 0-1 range for Canvas
            score = self.score if self.score is not None else 0.0
            score = score / 100.0  # Convert percentage to decimal
            print(f"Submitting score: {score}")
            
            # Create OAuth1 client and submit grade
            client = Client(
                client_key=consumer_key,
                client_secret=consumer_secret,
            )
            
            # Prepare the XML payload
            xml_template = """
            <?xml version="1.0" encoding="UTF-8"?>
            <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                <imsx_POXHeader>
                    <imsx_POXRequestHeaderInfo>
                        <imsx_version>V1.0</imsx_version>
                        <imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>
                    </imsx_POXRequestHeaderInfo>
                </imsx_POXHeader>
                <imsx_POXBody>
                    <replaceResultRequest>
                        <resultRecord>
                            <sourcedGUID>
                                <sourcedId>{sourcedid}</sourcedId>
                            </sourcedGUID>
                            <result>
                                <resultScore>
                                    <language>en</language>
                                    <textString>{score}</textString>
                                </resultScore>
                            </result>
                        </resultRecord>
                    </replaceResultRequest>
                </imsx_POXBody>
            </imsx_POXEnvelopeRequest>
            """.format(
                message_id=str(uuid.uuid4()),
                sourcedid=self.lis_result_sourcedid,
                score=str(score)
            )
            
            # Generate OAuth1 signature
            oauth_params = client.get_oauth_params()
            oauth_params.append(('oauth_body_hash', signature.sign_plaintext(xml_template, consumer_secret)))
            
            # Get authorization header
            auth_header = client.get_oauth_signature(
                self.lis_outcome_service_url,
                http_method='POST',
                oauth_params=oauth_params
            )
            
            headers = {
                'Content-Type': 'application/xml',
                'Authorization': auth_header,
            }
            
            # Send the request
            response = requests.post(
                self.lis_outcome_service_url,
                data=xml_template,
                headers=headers,
                verify=True
            )
            
            success = 200 <= response.status_code < 300
            if not success:
                logger.error(f"Failed to submit grade. Status: {response.status_code}, Response: {response.text}")
            return success
            
        except Exception as e:
            logger.error(f"Error submitting grade to Canvas: {str(e)}")
            return False

class StudentScore(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lis_result_sourcedid = models.CharField(max_length=255)
    score = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

class CaliperEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    event_type = models.CharField(max_length=255)
    event_data = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)

class EnrollmentCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    email = models.EmailField()
    course_instance = models.ForeignKey(CourseInstance, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        unique_together = ('email', 'course_instance')

    def __str__(self):
        return f"Code for {self.email} - {self.course_instance}"

class CourseProgress(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='course_progress')
    overall_progress = models.FloatField(default=0.0)
    overall_score = models.FloatField(default=0.0)
    modules_completed = models.IntegerField(default=0)
    total_modules = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)
    lis_result_sourcedid = models.CharField(max_length=255, null=True, blank=True)

    def update_progress(self):
        """Calculate overall course progress based on module progress"""
        print("\nUpdating CourseProgress...")
        module_progress = ModuleProgress.objects.filter(enrollment=self.enrollment)
        total_modules = Module.objects.filter(
            unit__course=self.enrollment.course_instance.course
        ).count()
        
        if total_modules > 0:
            completed = module_progress.filter(is_complete=True).count()
            print(f"Completed modules: {completed}")
            total_progress = sum(getattr(mp, 'progress', 0) or 0 for mp in module_progress)
            print(f"Total progress: {total_progress}")
            total_score = sum(getattr(mp, 'score', 0) or 0 for mp in module_progress)
            print(f"Total score: {total_score}")
            
            self.modules_completed = completed
            self.total_modules = total_modules
            self.overall_progress = (total_progress / total_modules) * 100 if total_modules > 0 else 0
            self.overall_score = (total_score / total_modules) if total_modules > 0 else 0
            self.save()
            
            # Submit grade to Canvas
            print("Checking LTI credentials for grade submission...")
            print(f"lis_result_sourcedid: {self.lis_result_sourcedid}")
            print(f"lis_outcome_service_url: {self.enrollment.course_instance.lis_outcome_service_url}")
            
            if self.lis_result_sourcedid and self.enrollment.course_instance.lis_outcome_service_url:
                print(f"Attempting to submit overall score: {self.overall_score}")
                self.submit_grade_to_canvas()
            else:
                print("Missing LTI credentials for grade submission")

    def submit_grade_to_canvas(self):
        """Submit the overall course grade back to Canvas"""
        print("Submitting grade to Canvas COURSE PROGRESS!")
        if not (self.lis_result_sourcedid and self.enrollment.course_instance.lis_outcome_service_url):
            logger.warning("Missing LTI grade passback credentials")
            return False
        
        try:
            # Get LTI 1.1 credentials
            consumer_key = settings.LTI_11_CONSUMER_KEY
            consumer_secret = settings.LTI_11_CONSUMER_SECRET
            print(f"Using consumer key: {consumer_key}")
            
            # Convert score to 0-1 range for Canvas
            score = self.overall_score / 100.0
            print(f"Submitting score: {score}")
            
            # Create the XML payload
            xml_template = """
            <?xml version="1.0" encoding="UTF-8"?>
            <imsx_POXEnvelopeRequest xmlns="http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
                <imsx_POXHeader>
                    <imsx_POXRequestHeaderInfo>
                        <imsx_version>V1.0</imsx_version>
                        <imsx_messageIdentifier>{message_id}</imsx_messageIdentifier>
                    </imsx_POXRequestHeaderInfo>
                </imsx_POXHeader>
                <imsx_POXBody>
                    <replaceResultRequest>
                        <resultRecord>
                            <sourcedGUID>
                                <sourcedId>{sourcedid}</sourcedId>
                            </sourcedGUID>
                            <result>
                                <resultScore>
                                    <language>en</language>
                                    <textString>{score}</textString>
                                </resultScore>
                            </result>
                        </resultRecord>
                    </replaceResultRequest>
                </imsx_POXBody>
            </imsx_POXEnvelopeRequest>
            """.format(
                message_id=str(uuid.uuid4()),
                sourcedid=self.lis_result_sourcedid,
                score=str(score)
            )

            # Calculate body hash
            body_hash = base64.b64encode(hashlib.sha1(xml_template.encode('utf-8')).digest()).decode('utf-8')
            
            # Prepare OAuth parameters
            oauth_timestamp = str(int(time.time()))
            oauth_nonce = str(uuid.uuid4())
            
            params = {
                'oauth_consumer_key': consumer_key,
                'oauth_signature_method': 'HMAC-SHA1',
                'oauth_timestamp': oauth_timestamp,
                'oauth_nonce': oauth_nonce,
                'oauth_version': '1.0',
                'oauth_body_hash': body_hash
            }

            # Generate base string
            base_string_parts = [
                'POST',
                quote(self.enrollment.course_instance.lis_outcome_service_url, safe=''),
                quote(urlencode(sorted(params.items())), safe='')
            ]
            base_string = '&'.join(base_string_parts)
            
            # Generate signature
            key = f"{quote(consumer_secret, safe='')}&"
            signature = base64.b64encode(
                hmac.new(
                    key.encode('utf-8'),
                    base_string.encode('utf-8'),
                    hashlib.sha1
                ).digest()
            ).decode('utf-8')
            
            # Add signature to params
            params['oauth_signature'] = signature
            
            # Create Authorization header
            auth_header = 'OAuth ' + ','.join(
                f'{quote(k, safe="~")}="{quote(v, safe="~")}"'
                for k, v in sorted(params.items())
            )
            
            headers = {
                'Content-Type': 'application/xml',
                'Authorization': auth_header,
            }
            
            print(f"Sending grade to: {self.enrollment.course_instance.lis_outcome_service_url}")
            print(f"Authorization header: {auth_header}")
            
            response = requests.post(
                self.enrollment.course_instance.lis_outcome_service_url,
                data=xml_template,
                headers=headers,
                verify=True
            )
            
            success = 200 <= response.status_code < 300
            print(f"Grade submission response: {response.status_code}")
            print(f"Response content: {response.text}")
            
            if not success:
                logger.error(f"Failed to submit grade. Status: {response.status_code}, Response: {response.text}")
            return success
            
        except Exception as e:
            logger.error(f"Error submitting grade to Canvas: {str(e)}")
            return False

@receiver(post_save, sender=Enrollment)
def create_module_progress_records(sender, instance, created, **kwargs):
    """
    Create ModuleProgress records for each module in the course when a new enrollment is created
    """
    if created:
        # Get total modules for the course
        total_modules = Module.objects.filter(unit__course=instance.course_instance.course).count()
        
        # Create or update CourseProgress with correct total_modules
        CourseProgress.objects.get_or_create(
            enrollment=instance,
            defaults={
                'total_modules': total_modules,
                'modules_completed': 0
            }
        )
        
        # Create ModuleProgress records
        module_progress_list = []
        modules = Module.objects.filter(unit__course=instance.course_instance.course)
        
        for module in modules:
            module_progress_list.append(
                ModuleProgress(
                    user=instance.student,
                    module=module,
                    enrollment=instance
                )
            )
        ModuleProgress.objects.bulk_create(module_progress_list)
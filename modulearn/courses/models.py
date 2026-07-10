from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.db.models.functions import Lower
from django.db.models.signals import post_save
from django.dispatch import receiver
import json
import requests
from oauthlib.oauth1 import Client
from oauthlib.oauth1.rfc5849 import signature
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
import logging
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
    is_locked_for_research = models.BooleanField(default=False)
    plugin_config = models.JSONField(default=dict, blank=True)
    instructors = models.ManyToManyField(User, related_name='courses_taught', limit_choices_to={'is_instructor': True}, blank=True)

    def __str__(self):
        return self.title

    def total_modules(self):
        """Return the total number of modules in the course."""
        return Module.objects.filter(unit__course=self).count()

    def is_plugin_enabled(self, plugin_key):
        from modulearn.learning.services.course_plugins import is_course_plugin_enabled
        return is_course_plugin_enabled(self, plugin_key)

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
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_visible = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    unlock_rule = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    @property
    def unlock_rule_type(self):
        conditions = (self.unlock_rule or {}).get('conditions') or []
        return conditions[0].get('type', 'none') if conditions else 'none'

    @property
    def unlock_rule_target(self):
        conditions = (self.unlock_rule or {}).get('conditions') or []
        return conditions[0].get('target_id', '') if conditions else ''

    class Meta:
        ordering = ['order', 'id']

class Module(models.Model):
    MODULE_TYPE_IMPORTED = 'imported'
    MODULE_TYPE_EXTERNAL_LINK = 'external_link'
    MODULE_TYPE_SPLICE_SMART_CONTENT = 'splice_smart_content'
    MODULE_TYPE_FILE = 'file'
    MODULE_TYPE_FORM = 'form'
    MODULE_TYPE_CHOICES = [
        (MODULE_TYPE_IMPORTED, 'Imported Activity'),
        (MODULE_TYPE_EXTERNAL_LINK, 'External Link'),
        (MODULE_TYPE_SPLICE_SMART_CONTENT, 'SPLICE Smart Learning Content'),
        (MODULE_TYPE_FILE, 'Uploaded File'),
        (MODULE_TYPE_FORM, 'Form / Survey'),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='modules', null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    module_type = models.CharField(max_length=32, choices=MODULE_TYPE_CHOICES, default=MODULE_TYPE_IMPORTED)
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_visible = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)
    unlock_rule = models.JSONField(default=dict, blank=True)
    content_data = models.JSONField(blank=True, null=True)
    content_url = models.URLField(blank=True, null=True)
    content_file = models.FileField(upload_to='course_modules/%Y/%m/', blank=True, null=True)
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

    @property
    def unlock_rule_type(self):
        conditions = (self.unlock_rule or {}).get('conditions') or []
        return conditions[0].get('type', 'none') if conditions else 'none'

    @property
    def unlock_rule_target(self):
        conditions = (self.unlock_rule or {}).get('conditions') or []
        return conditions[0].get('target_id', '') if conditions else ''

    def get_student_progress(self, user):
        try:
            return ModuleProgress.objects.get(
                enrollment__student=user,
                enrollment__course_instance__course=self.unit.course,
                module=self
            )
        except ModuleProgress.DoesNotExist:
            return None

    class Meta:
        indexes = [
            models.Index(fields=['resource_link_id']),
            models.Index(fields=['module_type', 'is_visible']),
        ]
        ordering = ['order', 'id']

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


class ModuleBranchRule(models.Model):
    CONDITION_SUCCESS = 'success'
    CONDITION_FAILURE = 'failure'
    CONDITION_COMPLETED = 'completed'
    CONDITION_SCORE_GTE = 'score_gte'
    CONDITION_SCORE_LT = 'score_lt'
    CONDITION_CHOICES = [
        (CONDITION_SUCCESS, 'Correct / Successful'),
        (CONDITION_FAILURE, 'Incorrect / Unsuccessful'),
        (CONDITION_COMPLETED, 'Completed'),
        (CONDITION_SCORE_GTE, 'Score At Least'),
        (CONDITION_SCORE_LT, 'Score Below'),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='branch_rules')
    source_module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='branch_source_rules')
    target_module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='branch_target_rules')
    condition_type = models.CharField(max_length=32, choices=CONDITION_CHOICES)
    threshold = models.FloatField(null=True, blank=True)
    priority = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['course', 'active'], name='branch_course_active_idx'),
            models.Index(fields=['source_module', 'active'], name='branch_source_active_idx'),
            models.Index(fields=['target_module', 'active'], name='branch_target_active_idx'),
        ]
        ordering = ['source_module_id', 'priority', 'id']

    def __str__(self):
        return f"If {self.source_module.title} {self.get_condition_type_display()} unlock {self.target_module.title}"


class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course_instance = models.ForeignKey(CourseInstance, on_delete=models.CASCADE, related_name='enrollments')
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'course_instance')

    def __str__(self):
        return f"{self.student.username} - {self.course_instance}"


class EnrollmentModuleUnlock(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='dynamic_module_unlocks')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='dynamic_unlocks')
    source_module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True, related_name='dynamic_unlock_sources')
    source_rule = models.ForeignKey(ModuleBranchRule, on_delete=models.CASCADE, null=True, blank=True, related_name='unlock_events')
    reason = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('enrollment', 'module', 'source_rule')
        indexes = [
            models.Index(fields=['enrollment', 'module'], name='unlock_enroll_module_idx'),
            models.Index(fields=['source_rule', 'created_at'], name='unlock_rule_created_idx'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.enrollment} unlocked {self.module.title}"

class ModuleProgress(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='module_progress', null=True, blank=True)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Progress tracking
    progress = models.FloatField(default=0.0, help_text='Progress between 0 and 1')
    is_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
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
        from modulearn.learning.services.progress import apply_progress_snapshot

        apply_progress_snapshot(
            self,
            source='manual',
            progress=new_progress,
            is_complete=new_progress >= 1.0,
        )

    def update_from_activity_attempt(self, data):
        """Update progress based on activity attempt data"""
        if not isinstance(data, dict) or 'data' not in data or not data['data']:
            logger.warning("Invalid activity attempt payload for module progress update")
            return
        
        activity_data = data['data'][0]  # Get the first activity
        
        # Update fields from the activity data
        try:
            from modulearn.learning.services.progress import apply_progress_snapshot

            progress_value = None
            if 'completion' in activity_data and bool(activity_data['completion']):
                progress_value = 1.0
            elif 'progress' in activity_data:
                progress_value = float(activity_data['progress']) / 100.0

            score_value = float(activity_data['score']) if 'score' in activity_data else self.score

            apply_progress_snapshot(
                self,
                source='splice',
                progress=progress_value,
                score=score_value,
                success=bool(activity_data['success']) if 'success' in activity_data else self.success,
                is_complete=bool(activity_data['completion']) if 'completion' in activity_data else None,
                payload=activity_data.get('response'),
                event_type='progress',
            )

            self.attempts = (self.attempts or 0) + 1
            self.last_response = json.dumps(activity_data)
            self.save(update_fields=['attempts', 'last_response', 'last_accessed'])
        except Exception as e:
            logger.error(f"Error updating module progress: {str(e)}")
            raise

    def submit_grade_to_canvas(self):
        """Submit grade to Canvas via LTI 1.1 or 1.3"""
        if not (self.lis_result_sourcedid and self.lis_outcome_service_url):
            logger.warning("Missing LTI grade passback credentials")
            return False
        
        try:
            # Get LTI 1.1 credentials
            consumer_key = settings.LTI_11_CONSUMER_KEY
            consumer_secret = settings.LTI_11_CONSUMER_SECRET
            
            # Convert score to 0-1 range for Canvas
            score = self.score if self.score is not None else 0.0
            score = score / 100.0  # Convert percentage to decimal
            
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
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                "course_instance",
                name="courses_enrollmentcode_email_instance_ci_unique",
            ),
        ]

    def clean(self):
        from accounts.email_utils import normalize_email_address

        super().clean()
        self.email = normalize_email_address(self.email)
        if (
            self.email
            and self.course_instance_id
            and type(self).objects.exclude(pk=self.pk).filter(
                email__iexact=self.email,
                course_instance_id=self.course_instance_id,
            ).exists()
        ):
            raise ValidationError({
                "email": "An enrollment code already exists for this email and course session.",
            })

    def save(self, *args, **kwargs):
        from accounts.email_utils import normalize_email_address

        normalized_email = normalize_email_address(self.email)
        email_changed = normalized_email != self.email
        self.email = normalized_email
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and email_changed:
            kwargs["update_fields"] = set(update_fields) | {"email"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Code for {self.email} - {self.course_instance}"

class CourseProgress(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='course_progress')
    overall_progress = models.FloatField(default=0.0)
    overall_score = models.FloatField(default=0.0)
    modules_completed = models.IntegerField(default=0)
    total_modules = models.IntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    lis_result_sourcedid = models.CharField(max_length=255, null=True, blank=True)

    def update_progress(self):
        """Calculate overall course progress based on module progress"""
        from modulearn.learning.services.progress import recompute_course_progress

        refreshed = recompute_course_progress(self.enrollment)
        self.overall_progress = refreshed.overall_progress
        self.overall_score = refreshed.overall_score
        self.modules_completed = refreshed.modules_completed
        self.total_modules = refreshed.total_modules
        self.completed_at = refreshed.completed_at
        if self.lis_result_sourcedid and self.enrollment.course_instance.lis_outcome_service_url:
            self.submit_grade_to_canvas()
        return refreshed

    def submit_grade_to_canvas(self):
        """Submit the overall course grade back to Canvas"""
        if not (self.lis_result_sourcedid and self.enrollment.course_instance.lis_outcome_service_url):
            logger.warning("Missing LTI grade passback credentials")
            return False
        
        try:
            # Get LTI 1.1 credentials
            consumer_key = settings.LTI_11_CONSUMER_KEY
            consumer_secret = settings.LTI_11_CONSUMER_SECRET
            
            # Convert score to 0-1 range for Canvas
            score = self.overall_score / 100.0
            
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
            
            response = requests.post(
                self.enrollment.course_instance.lis_outcome_service_url,
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


class ModuleForm(models.Model):
    module = models.OneToOneField(Module, on_delete=models.CASCADE, related_name='form')
    instructions = models.TextField(blank=True)
    allow_resubmission = models.BooleanField(default=False)
    submit_button_label = models.CharField(max_length=64, default='Submit')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Form for {self.module.title}"


class ModuleFormQuestion(models.Model):
    TYPE_LIKERT = 'likert'
    TYPE_SINGLE_CHOICE = 'single_choice'
    TYPE_MULTIPLE_CHOICE = 'multiple_choice'
    TYPE_SHORT_ANSWER = 'short_answer'
    TYPE_LONG_ANSWER = 'long_answer'
    TYPE_CHOICES = [
        (TYPE_LIKERT, 'Likert'),
        (TYPE_SINGLE_CHOICE, 'Multiple Choice - One Answer'),
        (TYPE_MULTIPLE_CHOICE, 'Multiple Choice - Multiple Answers'),
        (TYPE_SHORT_ANSWER, 'Short Answer'),
        (TYPE_LONG_ANSWER, 'Long Answer'),
    ]

    form = models.ForeignKey(ModuleForm, on_delete=models.CASCADE, related_name='questions')
    prompt = models.TextField()
    help_text = models.CharField(max_length=255, blank=True)
    question_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    options = models.JSONField(default=list, blank=True)
    likert_min_label = models.CharField(max_length=64, blank=True, default='Strongly disagree')
    likert_max_label = models.CharField(max_length=64, blank=True, default='Strongly agree')

    class Meta:
        ordering = ['order', 'id']
        indexes = [
            models.Index(fields=['form', 'order']),
        ]

    def __str__(self):
        return f"{self.form.module.title}: {self.prompt[:40]}"


class ModuleFormSubmission(models.Model):
    form = models.ForeignKey(ModuleForm, on_delete=models.CASCADE, related_name='submissions')
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='form_submissions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_form_submissions')
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_complete = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['form', 'submitted_at']),
            models.Index(fields=['enrollment', 'submitted_at']),
            models.Index(fields=['user', 'submitted_at']),
        ]
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.user.username} submission for {self.form.module.title}"


class ModuleFormAnswer(models.Model):
    submission = models.ForeignKey(ModuleFormSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ModuleFormQuestion, on_delete=models.CASCADE, related_name='answers')
    value = models.JSONField(default=dict, blank=True)
    text_value = models.TextField(blank=True)

    class Meta:
        unique_together = ('submission', 'question')

    def __str__(self):
        return f"Answer to {self.question_id} in submission {self.submission_id}"


class ModuleAccessLog(models.Model):
    EVENT_VIEW = 'view'
    EVENT_LAUNCH = 'launch'
    EVENT_DOWNLOAD = 'download'
    EVENT_FORM_SUBMIT = 'form_submit'
    EVENT_UNLOCK_DENIED = 'unlock_denied'
    EVENT_CHOICES = [
        (EVENT_VIEW, 'View'),
        (EVENT_LAUNCH, 'Launch'),
        (EVENT_DOWNLOAD, 'Download'),
        (EVENT_FORM_SUBMIT, 'Form Submit'),
        (EVENT_UNLOCK_DENIED, 'Unlock Denied'),
    ]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='module_access_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_access_logs')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='access_logs')
    course_instance = models.ForeignKey(CourseInstance, on_delete=models.CASCADE, related_name='module_access_logs')
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES, default=EVENT_VIEW)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['course_instance', 'created_at']),
            models.Index(fields=['module', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} {self.event_type} {self.module.title}"


class ModuleProgressEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('launch', 'Launch'),
        ('progress', 'Progress'),
        ('completion', 'Completion'),
        ('outcome', 'Outcome'),
        ('reopened', 'Reopened'),
    ]

    module_progress = models.ForeignKey(ModuleProgress, on_delete=models.CASCADE, related_name='events')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_progress_events')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='progress_events')
    course_instance = models.ForeignKey(
        CourseInstance,
        on_delete=models.CASCADE,
        related_name='progress_events',
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    source = models.CharField(max_length=64, default='system')
    progress = models.FloatField(default=0.0)
    score = models.FloatField(null=True, blank=True)
    success = models.BooleanField(default=False)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['course_instance', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} {self.event_type} {self.module.title}"

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

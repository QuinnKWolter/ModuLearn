from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
import json
import requests

User = get_user_model()

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

    def update_from_activity_attempt(self, data):
        """Update progress based on activity attempt data"""
        if not isinstance(data, dict) or 'data' not in data or not data['data']:
            return
        
        activity_data = data['data'][0]  # Get the first activity
        self.attempts += 1
        self.last_response = json.dumps(activity_data)
        
        # Update fields from the activity data with proper type conversion
        if 'score' in activity_data:
            self.score = float(activity_data['score'])
        if 'progress' in activity_data:
            self.progress = float(activity_data['progress']) / 100.0  # Convert percentage to decimal
        if 'success' in activity_data:
            self.success = bool(activity_data['success'])
        if 'completion' in activity_data:
            self.is_complete = bool(activity_data['completion'])
        if 'response' in activity_data:
            self.state_data = activity_data['response']
        
        self.save()
        
        # If LTI grade passback is configured, submit the grade
        if self.lis_result_sourcedid and self.lis_outcome_service_url:
            self.submit_grade_to_canvas()

    def submit_grade_to_canvas(self):
        """Submit grade to Canvas via LTI"""
        if not (self.lis_result_sourcedid and self.lis_outcome_service_url):
            return False
            
        score = self.score if self.score is not None else 0.0
        
        # Submit grade using LTI outcomes service
        payload = {
            'lis_result_sourcedid': self.lis_result_sourcedid,
            'score': score / 100.0  # Convert percentage to decimal
        }
        
        response = requests.post(
            self.lis_outcome_service_url,
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        return response.ok

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

    def update_progress(self):
        """Calculate overall course progress based on module progress"""
        module_progress = ModuleProgress.objects.filter(enrollment=self.enrollment)
        total_modules = Module.objects.filter(
            unit__course=self.enrollment.course_instance.course
        ).count()
        
        if total_modules > 0:
            completed = module_progress.filter(is_complete=True).count()
            total_progress = sum(mp.progress or 0 for mp in module_progress)
            total_score = sum(mp.score or 0 for mp in module_progress if mp.score is not None)
            
            self.modules_completed = completed
            self.total_modules = total_modules
            self.overall_progress = (total_progress / total_modules) * 100 if total_modules > 0 else 0
            self.overall_score = (total_score / total_modules) if total_modules > 0 else 0
            self.save()

@receiver(post_save, sender=Enrollment)
def create_module_progress_records(sender, instance, created, **kwargs):
    """
    Create ModuleProgress records for each module in the course when a new enrollment is created
    """
    if created:
        # Fix: Access course through course_instance
        modules = Module.objects.filter(unit__course=instance.course_instance.course)
        
        module_progress_list = []
        for module in modules:
            module_progress_list.append(
                ModuleProgress(
                    user=instance.student,
                    module=module,
                    enrollment=instance
                )
            )
        ModuleProgress.objects.bulk_create(module_progress_list)
        
        # Create CourseProgress
        CourseProgress.objects.create(enrollment=instance)
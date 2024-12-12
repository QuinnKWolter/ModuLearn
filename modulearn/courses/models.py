from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
import json

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

class Unit(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='units')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.course.title} - {self.title}"

class Module(models.Model):
    MODULE_TYPES = [
        ('quiz', 'Quiz'),
        ('coding', 'Coding Challenge'),
        ('simulation', 'Simulation'),
        ('external_iframe', 'External IFrame'),
    ]
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='modules', null=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    module_type = models.CharField(max_length=50, choices=MODULE_TYPES)
    content_data = models.JSONField(blank=True, null=True)
    content_url = models.URLField(blank=True, null=True)
    iframe_url = models.URLField(blank=True, null=True)
    keywords = models.CharField(max_length=500, blank=True)
    platform_name = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=255, blank=True)

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

class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'is_student': True})
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    date_enrolled = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.username} enrolled in {self.course.title}"

class ModuleProgress(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='module_progress')
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    
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
    
    class Meta:
        unique_together = ('enrollment', 'module')

    def __str__(self):
        return f"{self.enrollment.student.username} ({self.module}): {self.progress:.2f}% & {self.score or 0:.2f}"

    def update_from_activity_attempt(self, activity_data):
        """Update progress from activity attempt data"""
        # Update progress and completion based on the data
        self.progress = float(activity_data.get('progress', self.progress))
        self.is_complete = activity_data.get('completion', self.is_complete)
        self.score = float(activity_data.get('score', self.score or 0))
        self.success = activity_data.get('success', self.success)
        
        # Store the response data
        if 'response' in activity_data:
            try:
                response_data = json.loads(activity_data['response'])
                self.state_data = response_data
                self.last_response = activity_data['response']
            except json.JSONDecodeError:
                self.last_response = activity_data['response']
        
        self.attempts += 1
        self.save()

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
    code = models.CharField(max_length=255, unique=True)
    email = models.EmailField()
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} for {self.email} in {self.course.title}"

class CourseProgress(models.Model):
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='course_progress')
    
    overall_progress = models.FloatField(default=0.0)
    overall_score = models.FloatField(default=0.0)
    modules_completed = models.IntegerField(default=0)
    total_modules = models.IntegerField(default=0)
    
    last_accessed = models.DateTimeField(auto_now=True)
    
    @classmethod
    def get_or_create_progress(cls, enrollment):
        """Get or create course progress with proper initialization"""
        try:
            progress = enrollment.course_progress
        except CourseProgress.DoesNotExist:
            # Create new progress and initialize it
            progress = cls.objects.create(
                enrollment=enrollment,
                total_modules=Module.objects.filter(
                    unit__course=enrollment.course
                ).count()
            )
            progress.update_progress()  # Initialize progress
        return progress

    def update_progress(self):
        """Calculate overall course progress based on module progress"""
        module_progress = ModuleProgress.objects.filter(enrollment=self.enrollment)
        total_modules = Module.objects.filter(
            unit__course=self.enrollment.course
        ).count()
        
        completed = module_progress.filter(is_complete=True).count()
        total_progress = sum(mp.progress or 0 for mp in module_progress)
        total_score = sum(mp.score or 0 for mp in module_progress)
        
        self.modules_completed = completed
        self.total_modules = total_modules
        
        # Progress and score are already in percentages from the frontend
        self.overall_progress = total_progress / total_modules if total_modules > 0 else 0
        self.overall_score = total_score / total_modules if total_modules > 0 else 0
        self.save()

@receiver(post_save, sender=Enrollment)
def create_module_progress_records(sender, instance, created, **kwargs):
    if created:
        # Create ModuleProgress for each module in the course
        modules = Module.objects.filter(unit__course=instance.course)
        ModuleProgress.objects.bulk_create([
            ModuleProgress(enrollment=instance, module=module)
            for module in modules
        ])
        
        # Create CourseProgress
        CourseProgress.objects.create(enrollment=instance)
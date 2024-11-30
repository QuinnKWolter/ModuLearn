from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

class Course(models.Model):
    id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructors = models.ManyToManyField(User, related_name='courses_taught', limit_choices_to={'is_instructor': True}, blank=True)

    def __str__(self):
        return self.title

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

class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'is_student': True})
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    date_enrolled = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.username} enrolled in {self.course.title}"

class ModuleProgress(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='module_progress'
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE
    )
    is_complete = models.BooleanField(default=False)
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    last_accessed = models.DateTimeField(auto_now=True)
    progress_data = models.JSONField(
        blank=True,
        null=True,
        help_text='Store state data for resuming module progress.'
    )

    class Meta:
        unique_together = ('enrollment', 'module')

    def __str__(self):
        return f"{self.enrollment.student.username} - {self.module.title}"

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
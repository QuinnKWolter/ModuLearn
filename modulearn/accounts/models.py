from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    canvas_user_id = models.CharField(max_length=255, null=True, blank=True)
    is_instructor = models.BooleanField(default=False)
    is_student = models.BooleanField(default=True)
    full_name = models.CharField(max_length=100, blank=True, null=True)
    lti_data = models.JSONField(null=True, blank=True)
    course_authoring_password = models.CharField(max_length=255, null=True, blank=True)
    
    # KnowledgeTree integration fields
    kt_user_id = models.IntegerField(null=True, blank=True, unique=True,
                                     help_text="KnowledgeTree UserID (from database, may be None if only API used)")
    kt_login = models.CharField(max_length=255, null=True, blank=True, unique=True,
                               help_text="KnowledgeTree Login/Username (primary identifier)")
    kt_groups = models.JSONField(default=list, blank=True,
                                help_text="KnowledgeTree groups/courses the user belongs to")

    def __str__(self):
        return self.username

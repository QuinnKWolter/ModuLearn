from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    canvas_user_id = models.CharField(max_length=255, null=True, blank=True)
    is_instructor = models.BooleanField(default=False)
    is_student = models.BooleanField(default=True)
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    lti_data = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.username

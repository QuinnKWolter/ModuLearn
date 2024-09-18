# lti/models.py

from django.db import models
from django.contrib.auth import get_user_model
from courses.models import Course, Module

User = get_user_model()

class LTILaunch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True)
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True)
    id_token = models.TextField()
    state = models.CharField(max_length=255)
    nonce = models.CharField(max_length=255)
    issued_at = models.DateTimeField(auto_now_add=True)
    # Additional LTI parameters as needed

    def __str__(self):
        return f"LTI Launch for {self.user.username} at {self.issued_at}"

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from .email_utils import normalize_email_address


class User(AbstractUser):
    canvas_user_id = models.CharField(max_length=255, null=True, blank=True)
    is_instructor = models.BooleanField(default=False)
    is_student = models.BooleanField(default=True)
    is_anonymous_participant = models.BooleanField(default=False)
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

    def clean(self):
        super().clean()
        self.email = normalize_email_address(self.email)
        has_conflict = (
            self.email
            and type(self).objects.exclude(pk=self.pk).filter(email__iexact=self.email).exists()
        )
        original_email = ""
        if self.pk:
            original_email = normalize_email_address(
                type(self).objects.filter(pk=self.pk).values_list("email", flat=True).first()
            )
        if has_conflict and original_email != self.email:
            raise ValidationError({"email": "A user with this email address already exists."})

    def save(self, *args, **kwargs):
        normalized_email = normalize_email_address(self.email)
        email_changed = normalized_email != self.email
        self.email = normalized_email
        if self.is_instructor:
            self.is_student = False
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if self.is_instructor:
                update_fields.add("is_student")
            if email_changed:
                update_fields.add("email")
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

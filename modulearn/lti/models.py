"""
LTI Models for Tool Consumer functionality.

This module provides DB-backed caching for LTI launch contexts,
which are needed when processing outcome callbacks from LTI tools.
"""
from django.db import models
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class LTIPlatformRegistration(models.Model):
    """LTI 1.3 platform registration details for an LMS tenant."""

    PLATFORM_CANVAS = "canvas"
    PLATFORM_MOODLE = "moodle"
    PLATFORM_OTHER = "other"
    PLATFORM_CHOICES = [
        (PLATFORM_CANVAS, "Canvas"),
        (PLATFORM_MOODLE, "Moodle"),
        (PLATFORM_OTHER, "Other"),
    ]

    name = models.CharField(max_length=255)
    platform = models.CharField(max_length=32, choices=PLATFORM_CHOICES, default=PLATFORM_OTHER)
    issuer = models.URLField(max_length=512, help_text="Platform ID / issuer URL")
    client_id = models.CharField(max_length=255)
    deployment_ids = models.JSONField(default=list, blank=True)
    auth_login_url = models.URLField(max_length=512, help_text="Platform authentication request URL")
    auth_token_url = models.URLField(max_length=512, help_text="Platform access token URL")
    key_set_url = models.URLField(max_length=512, help_text="Platform public keyset URL")
    auth_audience = models.URLField(max_length=512, blank=True, default="")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "LTI 1.3 Platform Registration"
        verbose_name_plural = "LTI 1.3 Platform Registrations"
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "client_id"],
                name="lti_platform_registration_issuer_client_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["issuer", "client_id"]),
            models.Index(fields=["platform", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.client_id})"

    def deployment_id_list(self):
        if isinstance(self.deployment_ids, list):
            return [str(item).strip() for item in self.deployment_ids if str(item).strip()]
        if isinstance(self.deployment_ids, str):
            return [item.strip() for item in self.deployment_ids.split(",") if item.strip()]
        return []

    def to_tool_conf(self):
        return {
            "default": False,
            "client_id": self.client_id,
            "auth_login_url": self.auth_login_url,
            "auth_token_url": self.auth_token_url,
            "auth_audience": self.auth_audience or self.auth_token_url,
            "key_set_url": self.key_set_url,
            "key_set": None,
            "deployment_ids": self.deployment_id_list(),
        }


class LTIUserIdentity(models.Model):
    """Mapping between a platform-specific LTI user subject and a local user."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="lti_identities",
    )
    platform_registration = models.ForeignKey(
        LTIPlatformRegistration,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_identities",
    )
    issuer = models.CharField(max_length=512)
    client_id = models.CharField(max_length=255, blank=True, default="")
    deployment_id = models.CharField(max_length=255, blank=True, default="")
    subject = models.CharField(max_length=255)
    last_launch_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "LTI User Identity"
        verbose_name_plural = "LTI User Identities"
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "client_id", "subject"],
                name="lti_user_identity_unique_subject_per_client",
            ),
        ]
        indexes = [
            models.Index(fields=["issuer", "client_id"]),
            models.Index(fields=["subject"]),
        ]

    def __str__(self):
        return f"{self.issuer}:{self.subject} -> {self.user_id}"


class LTILaunchCache(models.Model):
    """
    Database-backed cache for LTI launch contexts.
    
    When we launch an LTI tool, we generate a source_id and cache the launch
    context (user, group, tool info, etc.). When the tool sends an outcome
    callback, we use the source_id to retrieve this context and forward the
    result to the User Modeling service AND update local ModuleProgress.
    
    This is DB-backed (not Django cache) for durability across multi-worker
    production deployments and server restarts.
    """
    # Primary identifier - format: "{usr}_{grp}_{sub}"
    source_id = models.CharField(max_length=512, unique=True, db_index=True)
    
    # Tool identification
    tool = models.CharField(max_length=64, help_text="Tool identifier (e.g., 'codecheck', 'ctat')")
    
    # User and context identifiers (these map to ModuLearn entities)
    usr = models.CharField(max_length=255, help_text="User ID (Django auth user ID)")
    grp = models.CharField(max_length=255, help_text="Group ID (CourseInstance ID)")
    sub = models.CharField(max_length=512, help_text="Activity identifier from tool URL")
    
    # ModuLearn entity IDs for local progress tracking
    module_id = models.IntegerField(null=True, blank=True, help_text="Module.id for progress updates")
    user_id = models.IntegerField(null=True, blank=True, help_text="Django User.id (parsed from usr)")
    course_instance_id = models.IntegerField(null=True, blank=True, help_text="CourseInstance.id (parsed from grp)")
    
    # Optional context fields for UM forwarding
    cid = models.CharField(max_length=255, blank=True, default='', help_text="Course ID")
    sid = models.CharField(max_length=255, blank=True, default='', help_text="Session ID")
    svc = models.CharField(max_length=255, blank=True, default='', help_text="Service identifier")
    
    # For debugging: store the resolved launch URL used
    launch_url = models.URLField(max_length=2048, blank=True, default='', 
                                  help_text="Resolved launch URL (for debugging)")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(db_index=True, 
                                       help_text="When this cache entry expires")
    
    class Meta:
        verbose_name = "LTI Launch Cache"
        verbose_name_plural = "LTI Launch Cache Entries"
        indexes = [
            models.Index(fields=['tool', 'usr', 'grp']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"LTI:{self.tool}:{self.source_id}"
    
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return timezone.now() > self.expires_at
    
    @classmethod
    def get_or_create_cache(cls, source_id: str, tool: str, usr: str, grp: str, 
                            sub: str, cid: str = '', sid: str = '', svc: str = '',
                            launch_url: str = '', ttl_hours: int = 24,
                            module_id: int = None) -> 'LTILaunchCache':
        """
        Get or create a cache entry, refreshing expiry on access.
        
        Args:
            source_id: Unique identifier for this launch (format: "{usr}_{grp}_{sub}")
            tool: Tool identifier
            usr: User identifier (Django user.id as string)
            grp: Group/context identifier (CourseInstance.id as string)
            sub: Activity/resource identifier (from tool URL)
            cid: Course ID (optional)
            sid: Session ID (optional)
            svc: Service identifier (optional)
            launch_url: Resolved launch URL (optional, for debugging)
            ttl_hours: Time-to-live in hours (default: 24)
            module_id: Module.id for local progress updates (optional but recommended)
            
        Returns:
            LTILaunchCache instance
        """
        expires_at = timezone.now() + timedelta(hours=ttl_hours)
        
        # Parse user_id and course_instance_id from usr/grp if they look like integers
        user_id = None
        course_instance_id = None
        try:
            user_id = int(usr) if usr and usr.isdigit() else None
        except (ValueError, TypeError):
            pass
        try:
            course_instance_id = int(grp) if grp and str(grp).isdigit() else None
        except (ValueError, TypeError):
            pass
        
        obj, created = cls.objects.update_or_create(
            source_id=source_id,
            defaults={
                'tool': tool,
                'usr': usr,
                'grp': grp,
                'sub': sub,
                'cid': cid or '',
                'sid': sid or '',
                'svc': svc or '',
                'launch_url': launch_url or '',
                'expires_at': expires_at,
                'module_id': module_id,
                'user_id': user_id,
                'course_instance_id': course_instance_id,
            }
        )
        
        action = "Created" if created else "Updated"
        logger.info(
            f"LTI Cache {action}: source_id={source_id}, tool={tool}, "
            f"module_id={module_id}, user_id={user_id}, instance_id={course_instance_id}"
        )
        
        return obj
    
    @classmethod
    def get_valid_cache(cls, source_id: str) -> 'LTILaunchCache | None':
        """
        Retrieve a cache entry if it exists and is not expired.
        
        Args:
            source_id: The source_id to look up
            
        Returns:
            LTILaunchCache instance or None if not found/expired
        """
        try:
            obj = cls.objects.get(source_id=source_id)
            if obj.is_expired():
                logger.warning(f"LTI cache entry expired: {source_id}")
                obj.delete()
                return None
            return obj
        except cls.DoesNotExist:
            logger.warning(f"LTI cache entry not found: {source_id}")
            return None
    
    @classmethod
    def cleanup_expired(cls) -> int:
        """
        Delete all expired cache entries.
        
        Returns:
            Number of entries deleted
        """
        count, _ = cls.objects.filter(expires_at__lt=timezone.now()).delete()
        if count > 0:
            logger.info(f"Cleaned up {count} expired LTI cache entries")
        return count


class LTIOutcomeLog(models.Model):
    """
    Log of LTI outcome callbacks received.
    
    Useful for debugging and auditing score submissions from tools.
    """
    source_id = models.CharField(max_length=512, db_index=True)
    tool = models.CharField(max_length=64, blank=True, default='')
    
    # Score information
    score_raw = models.CharField(max_length=64, help_text="Raw score string from tool")
    score_normalized = models.FloatField(null=True, blank=True, 
                                          help_text="Normalized score (0.0-1.0)")
    
    # Processing result
    success = models.BooleanField(default=False)
    um_url = models.URLField(max_length=2048, blank=True, default='',
                             help_text="UM service URL called")
    um_response_status = models.IntegerField(null=True, blank=True,
                                              help_text="HTTP status from UM service")
    error_message = models.TextField(blank=True, default='')
    
    # Timestamps
    received_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "LTI Outcome Log"
        verbose_name_plural = "LTI Outcome Logs"
        indexes = [
            models.Index(fields=['source_id']),
            models.Index(fields=['received_at']),
            models.Index(fields=['tool', 'received_at']),
        ]
    
    def __str__(self):
        status = "✓" if self.success else "✗"
        return f"{status} {self.tool}:{self.source_id} = {self.score_raw}"

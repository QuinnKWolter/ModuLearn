"""
Django Admin configuration for LTI models.
"""
from django.contrib import admin
from django.utils import timezone
from .models import LTILaunchCache, LTIOutcomeLog, LTIPlatformRegistration, LTIUserIdentity


@admin.register(LTIPlatformRegistration)
class LTIPlatformRegistrationAdmin(admin.ModelAdmin):
    list_display = [
        "name", "platform", "issuer", "client_id", "deployment_count",
        "is_active", "updated_at",
    ]
    list_filter = ["platform", "is_active", "created_at", "updated_at"]
    search_fields = ["name", "issuer", "client_id", "deployment_ids"]
    ordering = ["platform", "name"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = [
        ("Platform", {
            "fields": ["name", "platform", "is_active", "notes"],
        }),
        ("LTI 1.3 Identifiers", {
            "fields": ["issuer", "client_id", "deployment_ids"],
        }),
        ("Platform endpoints", {
            "fields": ["auth_login_url", "auth_token_url", "key_set_url", "auth_audience"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]

    @admin.display(description="Deployments")
    def deployment_count(self, obj):
        return len(obj.deployment_id_list())


@admin.register(LTIUserIdentity)
class LTIUserIdentityAdmin(admin.ModelAdmin):
    list_display = [
        "user", "issuer", "client_id", "deployment_id", "subject", "last_seen_at",
    ]
    list_filter = ["issuer", "client_id", "deployment_id", "created_at", "last_seen_at"]
    search_fields = ["user__username", "user__email", "issuer", "client_id", "subject"]
    readonly_fields = [
        "user", "platform_registration", "issuer", "client_id", "deployment_id",
        "subject", "last_launch_data", "created_at", "last_seen_at",
    ]
    ordering = ["-last_seen_at"]

    def has_add_permission(self, request):
        return False


@admin.register(LTILaunchCache)
class LTILaunchCacheAdmin(admin.ModelAdmin):
    """Admin for LTI Launch Cache entries."""
    
    list_display = [
        'source_id', 'tool', 'usr', 'grp', 'sub', 
        'created_at', 'expires_at', 'is_expired_display'
    ]
    list_filter = ['tool', 'created_at', 'expires_at']
    search_fields = ['source_id', 'usr', 'grp', 'sub']
    readonly_fields = ['source_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    
    fieldsets = [
        ('Identification', {
            'fields': ['source_id', 'tool']
        }),
        ('Launch Context', {
            'fields': ['usr', 'grp', 'sub', 'cid', 'sid', 'svc']
        }),
        ('Debug Info', {
            'fields': ['launch_url'],
            'classes': ['collapse']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at', 'expires_at']
        }),
    ]
    
    @admin.display(description='Expired?', boolean=True)
    def is_expired_display(self, obj):
        return obj.is_expired()
    
    actions = ['cleanup_expired']
    
    @admin.action(description='Delete expired cache entries')
    def cleanup_expired(self, request, queryset):
        count = LTILaunchCache.cleanup_expired()
        self.message_user(request, f"Cleaned up {count} expired entries.")


@admin.register(LTIOutcomeLog)
class LTIOutcomeLogAdmin(admin.ModelAdmin):
    """Admin for LTI Outcome Log entries."""
    
    list_display = [
        'received_at', 'tool', 'source_id', 'score_raw', 
        'score_normalized', 'success', 'um_response_status'
    ]
    list_filter = ['success', 'tool', 'received_at']
    search_fields = ['source_id', 'error_message']
    readonly_fields = [
        'source_id', 'tool', 'score_raw', 'score_normalized',
        'success', 'um_url', 'um_response_status', 'error_message', 'received_at'
    ]
    ordering = ['-received_at']
    
    fieldsets = [
        ('Request', {
            'fields': ['source_id', 'tool', 'received_at']
        }),
        ('Score', {
            'fields': ['score_raw', 'score_normalized']
        }),
        ('Processing', {
            'fields': ['success', 'um_url', 'um_response_status', 'error_message']
        }),
    ]
    
    def has_add_permission(self, request):
        # Logs should only be created programmatically
        return False
    
    def has_change_permission(self, request, obj=None):
        # Logs should be read-only
        return False

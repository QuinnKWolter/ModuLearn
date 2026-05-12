"""
Django Admin configuration for LTI models.
"""
from django.contrib import admin
from django.utils import timezone
from .models import LTILaunchCache, LTIOutcomeLog


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

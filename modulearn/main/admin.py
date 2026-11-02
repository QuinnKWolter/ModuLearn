from django.contrib import admin

from .models import TranslationReport


@admin.register(TranslationReport)
class TranslationReportAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'language', 'page_path', 'original_text', 'status')
    list_filter = ('status', 'language', 'created_at')
    search_fields = ('original_text', 'suggestion', 'page_path')
    readonly_fields = ('created_at', 'reporter', 'language', 'page_path', 'original_text', 'suggestion')
    actions = ['resolve', 'ignore']

    @admin.action(description='Mark selected reports resolved')
    def resolve(self, request, queryset):
        queryset.update(status='resolved')

    @admin.action(description='Ignore selected reports')
    def ignore(self, request, queryset):
        queryset.update(status='ignored')

    def has_add_permission(self, request):
        return False

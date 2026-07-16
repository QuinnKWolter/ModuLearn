from django.contrib import admin
from .models import (
    Course,
    CourseInstance,
    CourseProgress,
    Enrollment,
    EnrollmentModuleUnlock,
    EnrollmentCode,
    Module,
    ModuleAccessLog,
    ModuleBranchRule,
    ModuleForm,
    ModuleFormAnswer,
    ModuleFormQuestion,
    ModuleFormSubmission,
    ModuleProgress,
    StudentScore,
    Unit,
)

class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'description')
    search_fields = ('id', 'title', 'description')
    ordering = ('id',)

class CourseInstanceAdmin(admin.ModelAdmin):
    list_display = ('course', 'group_name')
    search_fields = ('course__title', 'group_name')

class EnrollmentCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'email', 'course_instance', 'created_at')
    search_fields = ('code', 'email', 'course_instance__course__title')


class UnitAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order', 'is_visible', 'is_locked')
    list_filter = ('is_visible', 'is_locked')
    search_fields = ('title', 'course__title')
    ordering = ('course', 'order', 'id')


class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'unit', 'module_type', 'order', 'is_visible', 'is_locked')
    list_filter = ('module_type', 'is_visible', 'is_locked')
    search_fields = ('title', 'unit__title', 'unit__course__title')
    ordering = ('unit', 'order', 'id')


class ModuleFormQuestionInline(admin.TabularInline):
    model = ModuleFormQuestion
    extra = 0


class ModuleFormAdmin(admin.ModelAdmin):
    list_display = ('module', 'allow_resubmission', 'updated_at')
    inlines = [ModuleFormQuestionInline]


class ModuleAccessLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'module', 'course_instance', 'event_type', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('user__username', 'module__title', 'course_instance__group_name')


class ModuleBranchRuleAdmin(admin.ModelAdmin):
    list_display = ('course', 'source_module', 'condition_type', 'required_study_condition', 'target_module', 'active', 'priority')
    list_filter = ('condition_type', 'required_study_condition', 'active')
    search_fields = ('course__title', 'source_module__title', 'target_module__title', 'required_study_condition')


class EnrollmentModuleUnlockAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'module', 'source_module', 'source_rule', 'created_at')
    search_fields = ('enrollment__student__username', 'module__title', 'source_module__title')

admin.site.register(Course, CourseAdmin)
admin.site.register(CourseInstance, CourseInstanceAdmin)
admin.site.register(Unit, UnitAdmin)
admin.site.register(Module, ModuleAdmin)
admin.site.register(Enrollment)
admin.site.register(EnrollmentCode, EnrollmentCodeAdmin)
admin.site.register(CourseProgress)
admin.site.register(ModuleProgress)
admin.site.register(StudentScore)
admin.site.register(ModuleForm, ModuleFormAdmin)
admin.site.register(ModuleFormSubmission)
admin.site.register(ModuleFormAnswer)
admin.site.register(ModuleAccessLog, ModuleAccessLogAdmin)
admin.site.register(ModuleBranchRule, ModuleBranchRuleAdmin)
admin.site.register(EnrollmentModuleUnlock, EnrollmentModuleUnlockAdmin)

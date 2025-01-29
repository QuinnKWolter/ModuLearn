from django.contrib import admin
from .models import Course, CourseInstance, Unit, Module, Enrollment, EnrollmentCode, CourseProgress, ModuleProgress, StudentScore

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

admin.site.register(Course, CourseAdmin)
admin.site.register(CourseInstance, CourseInstanceAdmin)
admin.site.register(Unit)
admin.site.register(Module)
admin.site.register(Enrollment)
admin.site.register(EnrollmentCode, EnrollmentCodeAdmin)
admin.site.register(CourseProgress)
admin.site.register(ModuleProgress)
admin.site.register(StudentScore)
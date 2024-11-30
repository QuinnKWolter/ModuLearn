from django.contrib import admin
from .models import Course, Unit, Module, Enrollment, EnrollmentCode

class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'description')
    search_fields = ('id', 'title', 'description')
    ordering = ('id',)

class EnrollmentCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'email', 'course', 'created_at')
    search_fields = ('code', 'email', 'course__title')

admin.site.register(Course, CourseAdmin)
admin.site.register(Unit)
admin.site.register(Module)
admin.site.register(Enrollment)
admin.site.register(EnrollmentCode, EnrollmentCodeAdmin)
from django.contrib import admin
from .models import Course, Unit, Module, Enrollment

class CourseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'description')
    search_fields = ('id', 'title', 'description')
    ordering = ('id',)

admin.site.register(Course, CourseAdmin)
admin.site.register(Unit)
admin.site.register(Module)
admin.site.register(Enrollment)
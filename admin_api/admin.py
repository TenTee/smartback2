from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Student, Trainer

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'enrollment_date')
    search_fields = ('first_name', 'last_name', 'email')

@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'expertise')
    search_fields = ('first_name', 'last_name', 'email', 'expertise')

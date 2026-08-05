from django.contrib import admin
from .models import File

@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "name", "size", "content_type", "created_at")
    search_fields = ("name", "owner__username", "owner__email")
    list_filter = ("content_type", "created_at")
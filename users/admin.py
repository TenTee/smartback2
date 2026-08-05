from django.contrib import admin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    readonly_fields = ("username", "date_created")
    exclude = ("password",)  # masque le champ mot de passe
    list_display = ("noms", "prenoms", "email", "username", "role", "is_active", "date_created")
    list_filter = ("role", "is_active")
    search_fields = ("noms", "prenoms", "email", "username")
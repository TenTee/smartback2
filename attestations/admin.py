from django.contrib import admin

from .models import DocumentDelivre


@admin.register(DocumentDelivre)
class DocumentDelivreAdmin(admin.ModelAdmin):
    list_display = ("numero", "type", "etudiant", "classe", "annee_academique", "delivre_le", "annule")
    list_filter = ("type", "annule", "canal")
    search_fields = ("numero", "etudiant__nom", "etudiant__matricule", "code")

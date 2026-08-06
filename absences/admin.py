from django.contrib import admin

from .models import DemandeAbsence


@admin.register(DemandeAbsence)
class DemandeAbsenceAdmin(admin.ModelAdmin):
    list_display = ["personnel", "date", "statut", "date_demande"]
    list_filter = ["statut", "date"]
    search_fields = ["personnel__nom", "motif"]

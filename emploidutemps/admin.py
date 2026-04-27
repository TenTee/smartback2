from django.contrib import admin
from .models import EmploiDuTemps

@admin.register(EmploiDuTemps)
class EmploiDuTempsAdmin(admin.ModelAdmin):
    list_display = ("formation", "module", "formateur", "jour", "heure_debut", "heure_fin", "salle")
    list_filter = ("jour", "formation", "formateur")
    search_fields = ("salle", "formation__nom", "module__nom", "formateur__nom")

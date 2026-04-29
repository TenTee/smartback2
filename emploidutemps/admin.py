from django.contrib import admin
from .models import EmploiDuTemps

@admin.register(EmploiDuTemps)
class EmploiDuTempsAdmin(admin.ModelAdmin):
    list_display = ("filiere", "niveau", "module", "formateur", "jour", "heure_debut", "heure_fin", "salle")
    list_filter = ("jour", "filiere", "niveau", "formateur")
    search_fields = ("salle", "filiere__nom", "module__nom", "formateur__nom")

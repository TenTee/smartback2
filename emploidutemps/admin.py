from django.contrib import admin
from .models import EmploiDuTemps, Salle

@admin.register(Salle)
class SalleAdmin(admin.ModelAdmin):
    list_display = ("nom", "capacite", "description", "created_at")
    search_fields = ("nom", "description")

@admin.register(EmploiDuTemps)
class EmploiDuTempsAdmin(admin.ModelAdmin):
    list_display = ("filiere", "niveau", "module", "formateur", "jour", "heure_debut", "heure_fin", "salle")
    list_filter = ("jour", "filiere", "niveau", "formateur")
    search_fields = ("salle__nom", "filiere__nom", "module__nom", "formateur__nom")


from .models import ActiviteClasse  # noqa: E402


@admin.register(ActiviteClasse)
class ActiviteClasseAdmin(admin.ModelAdmin):
    list_display = ("titre", "type", "jour", "date_debut", "date_fin", "heure_debut", "heure_fin", "recurrente")
    list_filter = ("type", "recurrente")
    filter_horizontal = ("classes",)

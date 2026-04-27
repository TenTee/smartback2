# modules/admin.py
from django.contrib import admin
from .models import Module

class ModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom', 'duree', 'get_formateurs')
    list_filter = ('duree',)  # ✅ tu ne peux plus filtrer sur formateur directement

    def get_formateurs(self, obj):
        # Retourne les noms des formateurs liés à ce module
        return ", ".join([f.nom for f in obj.formateurs.all()])
    get_formateurs.short_description = "Formateurs"

admin.site.register(Module, ModuleAdmin)
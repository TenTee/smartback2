from django.contrib import admin
from .models import DemandeArticle, LigneDemande


class LigneDemandeInline(admin.TabularInline):
    model = LigneDemande
    extra = 0


@admin.register(DemandeArticle)
class DemandeArticleAdmin(admin.ModelAdmin):
    list_display = ["reference", "objet", "statut", "priorite", "date_demande"]
    list_filter = ["statut", "priorite"]
    search_fields = ["reference", "objet"]
    readonly_fields = ["reference", "date_demande"]
    inlines = [LigneDemandeInline]

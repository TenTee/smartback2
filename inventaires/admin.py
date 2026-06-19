from django.contrib import admin
from .models import Article, Exemplaire, Mouvement, Inventaire


class ExemplaireInline(admin.TabularInline):
    model = Exemplaire
    extra = 0
    fields = ["reference", "statut", "condition", "localisation", "numero_serie"]
    readonly_fields = ["reference"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["reference", "nom", "categorie", "quantite_totale", "prix_unitaire"]
    list_filter = ["categorie"]
    search_fields = ["nom", "reference"]
    readonly_fields = ["reference"]
    inlines = [ExemplaireInline]


@admin.register(Exemplaire)
class ExemplaireAdmin(admin.ModelAdmin):
    list_display = ["reference", "article", "statut", "condition", "localisation"]
    list_filter = ["statut", "condition"]
    search_fields = ["reference", "article__nom", "numero_serie"]
    readonly_fields = ["reference"]


@admin.register(Mouvement)
class MouvementAdmin(admin.ModelAdmin):
    list_display = ["reference", "exemplaire", "type_mouvement", "date", "motif"]
    list_filter = ["type_mouvement"]
    readonly_fields = ["reference", "date"]


@admin.register(Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    list_display = ["reference", "article", "categorie", "statut"]
    list_filter = ["categorie", "statut"]
    readonly_fields = ["reference"]

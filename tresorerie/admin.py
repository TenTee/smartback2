from django.contrib import admin

from .models import CategorieFinance, ClotureCaisse, CompteTresorerie, Fournisseur, Operation

admin.site.register(CompteTresorerie)
admin.site.register(CategorieFinance)
admin.site.register(Fournisseur)
admin.site.register(ClotureCaisse)


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ("numero", "type", "date", "montant", "statut", "compte", "categorie", "source")
    list_filter = ("type", "statut", "source")
    search_fields = ("numero", "libelle", "tiers")

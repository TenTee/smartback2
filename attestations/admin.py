from django.contrib import admin

from .models import DemandeDocument, DocumentDelivre


@admin.register(DocumentDelivre)
class DocumentDelivreAdmin(admin.ModelAdmin):
    list_display = ("numero", "type", "etudiant", "classe", "annee_academique", "delivre_le", "annule")
    list_filter = ("type", "annule", "canal")
    search_fields = ("numero", "etudiant__nom", "etudiant__matricule", "code")


@admin.register(DemandeDocument)
class DemandeDocumentAdmin(admin.ModelAdmin):
    list_display = ("reference", "type", "etudiant", "statut", "cree_le", "traite_le")
    list_filter = ("type", "statut")
    search_fields = ("reference", "etudiant__nom", "etudiant__matricule")

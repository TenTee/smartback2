from django.contrib import admin
from .models import Etudiant, Inscription, EtudiantDocument, SanctionDisciplinaire

@admin.register(Etudiant)
class EtudiantAdmin(admin.ModelAdmin):
    list_display = ('nom', 'matricule', 'filiere', 'statut')
    search_fields = ('nom', 'matricule')
    list_filter = ('statut', 'filiere')

@admin.register(Inscription)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'classe', 'niveau', 'annee_academique')
    search_fields = ('etudiant__nom', 'classe__nom')

@admin.register(EtudiantDocument)
class EtudiantDocumentAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'type_document', 'date_upload')

@admin.register(SanctionDisciplinaire)
class SanctionDisciplinaireAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'type_sanction', 'date_sanction', 'active')
    list_filter = ('type_sanction', 'active')
    search_fields = ('etudiant__nom', 'motif')

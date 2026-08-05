from django.contrib import admin
from .models import (
    ParametresPaie, Paie, Prime, Retenue,
    AvanceSalaire, CampagnePaie, BulletinPaie
)


@admin.register(ParametresPaie)
class ParametresPaieAdmin(admin.ModelAdmin):
    list_display = ['jour_de_paie', 'taux_cnps_employe', 'taux_cnps_employeur', 'taux_irpp']


@admin.register(Paie)
class PaieAdmin(admin.ModelAdmin):
    list_display = ['beneficiaire', 'salaire', 'date', 'statut']
    list_filter = ['statut', 'date']


@admin.register(Prime)
class PrimeAdmin(admin.ModelAdmin):
    list_display = ['beneficiaire', 'type_prime', 'montant', 'est_permanente', 'est_active']
    list_filter = ['type_prime', 'est_active', 'est_permanente']


@admin.register(Retenue)
class RetenueAdmin(admin.ModelAdmin):
    list_display = ['beneficiaire', 'type_retenue', 'montant', 'est_permanente', 'est_active']
    list_filter = ['type_retenue', 'est_active', 'est_permanente']


@admin.register(AvanceSalaire)
class AvanceSalaireAdmin(admin.ModelAdmin):
    list_display = ['beneficiaire', 'montant_total', 'montant_rembourse', 'statut', 'date_demande']
    list_filter = ['statut']


@admin.register(CampagnePaie)
class CampagnePaieAdmin(admin.ModelAdmin):
    list_display = ['reference', 'mois', 'annee', 'statut', 'nombre_bulletins', 'total_net']
    list_filter = ['statut', 'annee']


@admin.register(BulletinPaie)
class BulletinPaieAdmin(admin.ModelAdmin):
    list_display = ['beneficiaire', 'mois', 'annee', 'salaire_base', 'salaire_net', 'statut']
    list_filter = ['statut', 'annee', 'mois']

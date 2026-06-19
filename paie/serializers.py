from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import (
    Paie, ParametresPaie, Prime, Retenue,
    AvanceSalaire, CampagnePaie, BulletinPaie
)


class PaieSerializer(serializers.ModelSerializer):
    beneficiaire_nom = serializers.SerializerMethodField()
    beneficiaire_salaire = serializers.SerializerMethodField()
    beneficiaire_type = serializers.SerializerMethodField()
    justificatif_url = serializers.SerializerMethodField()

    class Meta:
        model = Paie
        fields = [
            "id", "beneficiaire_content_type", "beneficiaire_object_id",
            "beneficiaire_nom", "beneficiaire_salaire", "beneficiaire_type",
            "salaire", "date", "statut", "justificatif", "justificatif_url",
        ]

    def get_beneficiaire_nom(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "nom", None)
        return None

    def get_beneficiaire_salaire(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "salaire", None)
        return None

    def get_beneficiaire_type(self, obj):
        if obj.beneficiaire_content_type:
            return obj.beneficiaire_content_type.model
        return None

    def get_justificatif_url(self, obj):
        request = self.context.get("request")
        if obj.justificatif and hasattr(obj.justificatif, "url") and request:
            return request.build_absolute_uri(obj.justificatif.url)
        return None


class ParametresPaieSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametresPaie
        fields = '__all__'


class PrimeSerializer(serializers.ModelSerializer):
    beneficiaire_nom = serializers.SerializerMethodField()
    beneficiaire_type = serializers.SerializerMethodField()
    type_prime_display = serializers.CharField(source='get_type_prime_display', read_only=True)

    class Meta:
        model = Prime
        fields = [
            "id", "beneficiaire_content_type", "beneficiaire_object_id",
            "beneficiaire_nom", "beneficiaire_type",
            "type_prime", "type_prime_display", "libelle", "montant",
            "est_permanente", "date_debut", "date_fin", "est_active",
        ]

    def get_beneficiaire_nom(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "nom", None)
        return None

    def get_beneficiaire_type(self, obj):
        if obj.beneficiaire_content_type:
            return obj.beneficiaire_content_type.model
        return None


class RetenueSerializer(serializers.ModelSerializer):
    beneficiaire_nom = serializers.SerializerMethodField()
    beneficiaire_type = serializers.SerializerMethodField()
    type_retenue_display = serializers.CharField(source='get_type_retenue_display', read_only=True)

    class Meta:
        model = Retenue
        fields = [
            "id", "beneficiaire_content_type", "beneficiaire_object_id",
            "beneficiaire_nom", "beneficiaire_type",
            "type_retenue", "type_retenue_display", "libelle", "montant",
            "est_permanente", "date_debut", "date_fin", "est_active",
        ]

    def get_beneficiaire_nom(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "nom", None)
        return None

    def get_beneficiaire_type(self, obj):
        if obj.beneficiaire_content_type:
            return obj.beneficiaire_content_type.model
        return None


class AvanceSalaireSerializer(serializers.ModelSerializer):
    beneficiaire_nom = serializers.SerializerMethodField()
    beneficiaire_type = serializers.SerializerMethodField()
    solde_restant = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = AvanceSalaire
        fields = [
            "id", "beneficiaire_content_type", "beneficiaire_object_id",
            "beneficiaire_nom", "beneficiaire_type",
            "montant_total", "montant_rembourse", "nombre_echeances",
            "montant_echeance", "motif", "date_demande",
            "date_debut_remboursement", "statut", "statut_display", "solde_restant",
        ]

    def get_beneficiaire_nom(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "nom", None)
        return None

    def get_beneficiaire_type(self, obj):
        if obj.beneficiaire_content_type:
            return obj.beneficiaire_content_type.model
        return None


class BulletinPaieSerializer(serializers.ModelSerializer):
    beneficiaire_nom = serializers.SerializerMethodField()
    beneficiaire_type = serializers.SerializerMethodField()
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = BulletinPaie
        fields = [
            "id", "campagne", "beneficiaire_content_type", "beneficiaire_object_id",
            "beneficiaire_nom", "beneficiaire_type",
            "mois", "annee", "salaire_base", "total_primes", "total_retenues",
            "salaire_brut", "salaire_net", "detail_primes", "detail_retenues",
            "statut", "statut_display", "date_generation", "date_paiement", "commentaire",
        ]

    def get_beneficiaire_nom(self, obj):
        if obj.beneficiaire:
            return getattr(obj.beneficiaire, "nom", None)
        return None

    def get_beneficiaire_type(self, obj):
        if obj.beneficiaire_content_type:
            return obj.beneficiaire_content_type.model
        return None


class CampagnePaieSerializer(serializers.ModelSerializer):
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    bulletins = BulletinPaieSerializer(many=True, read_only=True)

    class Meta:
        model = CampagnePaie
        fields = [
            "id", "reference", "mois", "annee", "statut", "statut_display",
            "date_creation", "date_validation", "date_paiement",
            "total_brut", "total_primes", "total_retenues", "total_net",
            "nombre_bulletins", "commentaire", "bulletins",
        ]


class CampagnePaieListSerializer(serializers.ModelSerializer):
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)

    class Meta:
        model = CampagnePaie
        fields = [
            "id", "reference", "mois", "annee", "statut", "statut_display",
            "date_creation", "date_validation", "date_paiement",
            "total_brut", "total_primes", "total_retenues", "total_net",
            "nombre_bulletins", "commentaire",
        ]

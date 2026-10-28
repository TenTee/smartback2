from rest_framework import serializers

from .models import DocumentDelivre
from .services import statut


class DocumentDelivreSerializer(serializers.ModelSerializer):
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    annee_libelle = serializers.CharField(source="annee_academique.libelle", read_only=True)
    delivre_par_nom = serializers.SerializerMethodField()
    statut = serializers.SerializerMethodField()

    class Meta:
        model = DocumentDelivre
        fields = [
            "id", "type", "type_libelle", "numero", "code", "etudiant", "etudiant_nom", "etudiant_matricule",
            "classe", "classe_nom", "annee_academique", "annee_libelle", "delivre_le", "delivre_par_nom", "canal",
            "valide_jusqu_au", "nb_impressions", "derniere_impression", "statut", "annule_le", "motif_annulation",
        ]

    def get_delivre_par_nom(self, obj):
        u = obj.delivre_par
        if obj.canal == "portail":
            return "Portail étudiant"
        if not u:
            return ""
        return f"{u.prenoms or ''} {u.noms or ''}".strip() or u.username

    def get_statut(self, obj):
        return statut(obj)

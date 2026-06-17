from rest_framework import serializers
from .models import Note


# Serializer détaillé (notes par module)
class NoteSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    evaluation_nom = serializers.CharField(source="evaluation.libelle", read_only=True)
    formation = serializers.CharField(source="etudiant.filiere.nom", read_only=True)
    session = serializers.CharField(read_only=True)
    note_sur_20 = serializers.SerializerMethodField()
    besoin_rattrapage = serializers.SerializerMethodField()

    class Meta:
        model = Note
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "etudiant_matricule",
            "formation",
            "classe",
            "classe_nom",
            "module",
            "module_nom",
            "evaluation",
            "evaluation_nom",
            "session",
            "note_cc",
            "note_sn",
            "note_rattrapage",
            "note_finale",
            "note_sur_20",   # ✅ ajouté
            "besoin_rattrapage",
        ]

    def get_note_sur_20(self, obj):
        return float(obj.note_finale) if obj.note_finale is not None else None

    def get_besoin_rattrapage(self, obj):
        return obj.besoin_rattrapage


# Serializer résumé (vue synthétique avec moyenne et mention)
class NoteSummarySerializer(serializers.Serializer):
    etudiant_id = serializers.IntegerField()
    etudiant_nom = serializers.CharField()
    etudiant_matricule = serializers.CharField()
    formation = serializers.CharField()
    session = serializers.CharField()
    moyenne_generale = serializers.FloatField()
    mention = serializers.CharField()


# Serializer pour les détails d’un étudiant dans un module
class NoteDetailSerializer(serializers.Serializer):
    module_id = serializers.IntegerField()
    module_nom = serializers.CharField()
    note_cc = serializers.FloatField(default=0)
    note_sn = serializers.FloatField(default=0)
    note_rattrapage = serializers.FloatField(default=0)
    note_finale = serializers.FloatField(default=0)
    note_sur_20 = serializers.FloatField(default=0)   # ✅ ajouté


# ✅ Sous-serializer pour les notes d’un étudiant dans un module
class EtudiantNoteSerializer(serializers.Serializer):
    module_id = serializers.IntegerField()
    module_nom = serializers.CharField()
    note_cc = serializers.FloatField(allow_null=True)
    note_sn = serializers.FloatField(allow_null=True)
    note_rattrapage = serializers.FloatField(allow_null=True)
    note_finale = serializers.FloatField(allow_null=True)
    note_sur_20 = serializers.FloatField(allow_null=True)   # ✅ ajouté


# ✅ Sous-serializer pour un étudiant dans une filière
class EtudiantFiliereSerializer(serializers.Serializer):
    etudiant_id = serializers.IntegerField()
    etudiant_nom = serializers.CharField()
    etudiant_matricule = serializers.CharField()
    session = serializers.CharField()
    notes = EtudiantNoteSerializer(many=True)


# ✅ Serializer principal pour les notes par filière
class NoteFiliereSerializer(serializers.Serializer):
    filiere_id = serializers.IntegerField()
    filiere_nom = serializers.CharField()
    modules = serializers.ListField(
        child=serializers.DictField()
    )
    etudiants = EtudiantFiliereSerializer(many=True)

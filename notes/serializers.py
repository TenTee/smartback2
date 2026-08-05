from rest_framework import serializers
from .models import Note


def validate_note_max_20(value):
    if value is not None and value > 20:
        raise serializers.ValidationError("La note ne peut pas dépasser 20.")
    if value is not None and value < 0:
        raise serializers.ValidationError("La note ne peut pas être négative.")
    return value


class NoteSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    module_semestre = serializers.SerializerMethodField()
    classe_nom = serializers.SerializerMethodField()
    evaluation_nom = serializers.SerializerMethodField()
    formation = serializers.SerializerMethodField()
    formateur_nom = serializers.SerializerMethodField()
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
            "module_semestre",
            "evaluation",
            "evaluation_nom",
            "session",
            "formateur_nom",
            "note_cc",
            "note_sn",
            "note_rattrapage",
            "note_finale",
            "note_sur_20",
            "besoin_rattrapage",
        ]
        read_only_fields = ["id", "note_finale", "session"]

    def validate_note_cc(self, value):
        return validate_note_max_20(value)

    def validate_note_sn(self, value):
        return validate_note_max_20(value)

    def validate_note_rattrapage(self, value):
        return validate_note_max_20(value)

    def get_note_sur_20(self, obj):
        return float(obj.note_finale) if obj.note_finale is not None else None

    def get_besoin_rattrapage(self, obj):
        return obj.besoin_rattrapage

    def get_classe_nom(self, obj):
        if obj.classe:
            return obj.classe.nom
        return None

    def get_evaluation_nom(self, obj):
        if obj.evaluation:
            return getattr(obj.evaluation, 'libelle', None) or str(obj.evaluation)
        return None

    def get_formation(self, obj):
        if obj.etudiant and obj.etudiant.filiere:
            return obj.etudiant.filiere.nom
        return None

    def get_module_semestre(self, obj):
        return getattr(obj.module, 'semestre', '') or obj.session or ''

    def get_formateur_nom(self, obj):
        if obj.classe_id and obj.module_id:
            from academique.models import Affectation
            aff = Affectation.objects.filter(
                module_id=obj.module_id,
                classe_id=obj.classe_id,
            ).select_related('enseignant').first()
            if aff and aff.enseignant:
                return aff.enseignant.nom or ""
        return ""


class NoteSummarySerializer(serializers.Serializer):
    etudiant_id = serializers.IntegerField()
    etudiant_nom = serializers.CharField()
    etudiant_matricule = serializers.CharField()
    formation = serializers.CharField(allow_null=True)
    session = serializers.CharField(allow_null=True)
    moyenne_generale = serializers.FloatField()
    mention = serializers.CharField()


class NoteDetailSerializer(serializers.Serializer):
    module_id = serializers.IntegerField()
    module_nom = serializers.CharField()
    note_cc = serializers.FloatField(allow_null=True)
    note_sn = serializers.FloatField(allow_null=True)
    note_rattrapage = serializers.FloatField(allow_null=True)
    note_finale = serializers.FloatField(allow_null=True)
    note_sur_20 = serializers.FloatField(allow_null=True)


class EtudiantNoteSerializer(serializers.Serializer):
    module_id = serializers.IntegerField()
    module_nom = serializers.CharField()
    note_cc = serializers.FloatField(allow_null=True)
    note_sn = serializers.FloatField(allow_null=True)
    note_rattrapage = serializers.FloatField(allow_null=True)
    note_finale = serializers.FloatField(allow_null=True)
    note_sur_20 = serializers.FloatField(allow_null=True)


class EtudiantFiliereSerializer(serializers.Serializer):
    etudiant_id = serializers.IntegerField()
    etudiant_nom = serializers.CharField()
    etudiant_matricule = serializers.CharField()
    session = serializers.CharField(allow_null=True)
    notes = EtudiantNoteSerializer(many=True)


class NoteFiliereSerializer(serializers.Serializer):
    filiere_id = serializers.IntegerField()
    filiere_nom = serializers.CharField()
    modules = serializers.ListField(child=serializers.DictField())
    etudiants = EtudiantFiliereSerializer(many=True)

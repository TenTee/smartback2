from rest_framework import serializers

from emploidutemps.models import EmploiDuTemps
from etudiants.models import Etudiant, Inscription
from modules.models import Module
from notes.models import Note
from paiements.models import Frais, Paiement

from .models import (
    Affectation,
    AnneeAcademique,
    Classe,
    ConfigurationEtablissement,
    CourseAssignment,
    Cycle,
    CycleGlobal,
    Departement,
    Epreuve,
    Evaluation,
    Filiere,
    Niveau,
    ParametresGlobaux,
    PreInscription,
    Semestre,
    UniversiteTutelle,
)


class ParametresGlobauxSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametresGlobaux
        fields = ["pourcentage_cc", "pourcentage_sn"]

    def validate(self, attrs):
        cc = attrs.get("pourcentage_cc", getattr(self.instance, "pourcentage_cc", 30))
        sn = attrs.get("pourcentage_sn", getattr(self.instance, "pourcentage_sn", 70))
        if cc + sn != 100:
            raise serializers.ValidationError("La somme de CC et SN doit être exactement 100%.")
        return attrs


class ConfigurationEtablissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationEtablissement
        fields = "__all__"


class CycleGlobalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CycleGlobal
        fields = ["id", "nom", "code", "description", "heure_pause_debut", "heure_pause_fin", "heure_debut_journee", "heure_fin_journee", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class CaseInsensitiveUniqueWithinParentMixin:
    parent_field = None
    model_class = None
    name_field = "nom"
    instance_id = None

    def validate_scoped_name(self, attrs):
        parent_field = self.parent_field
        model_class = self.model_class
        name_field = self.name_field
        instance = getattr(self, "instance", None)

        if not parent_field or not model_class or name_field not in attrs:
            return attrs

        parent_value = attrs.get(parent_field) or getattr(instance, parent_field, None)
        if parent_value is None:
            return attrs

        queryset = model_class.objects.filter(**{
            parent_field: parent_value,
            f"{name_field}__iexact": attrs[name_field].strip(),
        })
        if instance is not None:
            queryset = queryset.exclude(pk=instance.pk)

        if queryset.exists():
            raise serializers.ValidationError({
                name_field: "Une entité avec ce nom existe déjà dans ce périmètre.",
            })

        return attrs


class UniversiteTutelleSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = UniversiteTutelle
        fields = [
            "id",
            "nom",
            "name",
            "code",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "name"]


class DepartementSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Departement
    parent_field = "universite_tutelle"
    universite_tutelle_nom = serializers.CharField(source="universite_tutelle.nom", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Departement
        fields = [
            "id",
            "universite_tutelle",
            "universite_tutelle_nom",
            "nom",
            "name",
            "code",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "universite_tutelle_nom", "name"]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)


class FiliereSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Filiere
    parent_field = "departement"
    departement_nom = serializers.CharField(source="departement.nom", read_only=True)
    universite_tutelle_nom = serializers.CharField(source="departement.universite_tutelle.nom", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)
    # Affiche le nom du cycle (type de cycle) associé à la filière s'il y en a un
    cycle_nom = serializers.SerializerMethodField()
    # Nombre de niveaux créés sous cette filière
    nombre_niveaux = serializers.SerializerMethodField()

    class Meta:
        model = Filiere
        fields = [
            "id",
            "departement",
            "departement_nom",
            "universite_tutelle_nom",
            "nom",
            "name",
            "code",
            "responsable_nom",
            "description",
            "cycle_nom",
            "nombre_niveaux",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "departement_nom",
            "universite_tutelle_nom",
            "name",
            "cycle_nom",
            "nombre_niveaux",
        ]

    def get_cycle_nom(self, obj):
        """Retourne le nom du premier cycle de la filière (cycle principal)."""
        cycle = obj.cycles.select_related("type_cycle").first()
        if cycle:
            return cycle.type_cycle.nom if cycle.type_cycle else cycle.nom
        return None

    def get_nombre_niveaux(self, obj):
        """Retourne le nombre total de niveaux rattachés à cette filière."""
        from .models import Niveau
        return Niveau.objects.filter(cycle__filiere=obj).count()

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)


class CycleSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Cycle
    parent_field = "filiere"
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    departement_nom = serializers.CharField(source="filiere.departement.nom", read_only=True)
    levels_count = serializers.SerializerMethodField()
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Cycle
        fields = [
            "id",
            "filiere",
            "filiere_nom",
            "type_cycle",
            "departement_nom",
            "nom",
            "name",
            "code",
            "ordre",
            "description",
            "levels_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "filiere_nom",
            "departement_nom",
            "levels_count",
            "name",
        ]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)

    def get_levels_count(self, obj):
        return obj.niveaux.count()


class LevelSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Niveau
    parent_field = "cycle"
    cycle_nom = serializers.CharField(source="cycle.nom", read_only=True)
    filiere_id = serializers.IntegerField(source="cycle.filiere_id", read_only=True)
    filiere_nom = serializers.CharField(source="cycle.filiere.nom", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Niveau
        fields = [
            "id",
            "filiere_id",
            "filiere_nom",
            "cycle",
            "cycle_nom",
            "nom",
            "name",
            "code",
            "ordre",
            "modules",
        ]
        read_only_fields = [
            "id",
            "filiere_id",
            "filiere_nom",
            "cycle_nom",
            "name",
        ]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)


class CourseSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nom", read_only=True)
    filiere = serializers.PrimaryKeyRelatedField(queryset=Filiere.objects.all(), write_only=True, required=False)
    cycle = serializers.PrimaryKeyRelatedField(queryset=Cycle.objects.all(), write_only=True, required=False)
    niveau = serializers.PrimaryKeyRelatedField(queryset=Niveau.objects.all(), write_only=True, required=False)
    classe = serializers.PrimaryKeyRelatedField(queryset=Classe.objects.all(), write_only=True, required=False)
    attributions = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id",
            "nom",
            "name",
            "duree",
            "coefficient",
            "semestre",
            "filiere",
            "cycle",
            "niveau",
            "classe",
            "attributions",
        ]
        read_only_fields = ["id", "name"]

    def get_attributions(self, obj):
        return [
            {
                "id": attribution.id,
                "filiere_id": attribution.filiere_id,
                "filiere_nom": attribution.filiere.nom,
                "cycle_id": attribution.cycle_id,
                "cycle_nom": attribution.cycle.nom,
                "niveau_id": attribution.niveau_id,
                "niveau_nom": attribution.niveau.nom,
            }
            for attribution in obj.course_assignments.select_related("filiere", "cycle", "niveau").all()
        ]

    def create(self, validated_data):
        filiere = validated_data.pop("filiere", None)
        cycle = validated_data.pop("cycle", None)
        niveau = validated_data.pop("niveau", None)
        classe = validated_data.pop("classe", None)
        module = Module.objects.create(**validated_data)
        self._sync_assignment(module, filiere, cycle, niveau, classe)
        return module

    def update(self, instance, validated_data):
        filiere = validated_data.pop("filiere", serializers.empty)
        cycle = validated_data.pop("cycle", serializers.empty)
        niveau = validated_data.pop("niveau", serializers.empty)
        classe = validated_data.pop("classe", serializers.empty)
        module = super().update(instance, validated_data)
        if filiere is not serializers.empty or cycle is not serializers.empty or niveau is not serializers.empty or classe is not serializers.empty:
            self._sync_assignment(
                module,
                None if filiere is serializers.empty else filiere,
                None if cycle is serializers.empty else cycle,
                None if niveau is serializers.empty else niveau,
                None if classe is serializers.empty else classe,
                replace=True,
            )
        return module

    def _sync_assignment(self, module, filiere, cycle, niveau, classe=None, replace=False):
        if replace:
            module.course_assignments.all().delete()
            # Also clear from Classe if we want strict one-to-one or handle M2M
            if classe:
                classe.modules.add(module)
        
        if not all([filiere, cycle, niveau]):
            # If only classe is provided, we can try to infer others
            if classe:
                filiere = filiere or classe.filiere
                cycle = cycle or classe.cycle
                niveau = niveau or classe.niveau
                classe.modules.add(module)
            else:
                return
                
        CourseAssignment.objects.get_or_create(
            module=module,
            filiere=filiere,
            cycle=cycle,
            niveau=niveau,
        )

    def validate(self, attrs):
        filiere = attrs.get("filiere")
        cycle = attrs.get("cycle")
        niveau = attrs.get("niveau")

        if filiere and cycle and cycle.filiere_id != filiere.id:
            raise serializers.ValidationError({"cycle": "Le cycle doit appartenir à la filière sélectionnée."})
        if cycle and niveau and niveau.cycle_id != cycle.id:
            raise serializers.ValidationError({"niveau": "Le niveau doit appartenir au cycle sélectionné."})
        
        return attrs


class AnneeAcademiqueSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="libelle", read_only=True)

    class Meta:
        model = AnneeAcademique
        fields = [
            "id",
            "libelle",
            "name",
            "description",
            "date_debut",
            "date_fin",
            "est_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "name"]


class ClasseSerializer(serializers.ModelSerializer):
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    cycle_nom = serializers.CharField(source="cycle.nom", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)
    annee_academique_libelle = serializers.CharField(source="annee_academique.libelle", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Classe
        fields = [
            "id",
            "filiere",
            "filiere_nom",
            "cycle",
            "cycle_nom",
            "niveau",
            "niveau_nom",
            "annee_academique",
            "annee_academique_libelle",
            "nom",
            "name",
            "description",
            "modules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "nom",
            "name",
            "created_at",
            "updated_at",
            "filiere_nom",
            "cycle_nom",
            "niveau_nom",
            "annee_academique_libelle",
        ]


class SemestreSerializer(serializers.ModelSerializer):
    annee_academique_libelle = serializers.CharField(source="annee_academique.libelle", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Semestre
        fields = [
            "id",
            "annee_academique",
            "annee_academique_libelle",
            "nom",
            "name",
            "ordre",
            "description",
            "date_debut",
            "date_fin",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "annee_academique_libelle", "name"]


class EvaluationSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    semestre_nom = serializers.CharField(source="semestre.nom", read_only=True)
    name = serializers.CharField(source="libelle", read_only=True)

    class Meta:
        model = Evaluation
        fields = [
            "id",
            "classe",
            "classe_nom",
            "module",
            "module_nom",
            "semestre",
            "semestre_nom",
            "type_evaluation",
            "libelle",
            "name",
            "description",
            "coefficient",
            "date_evaluation",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "classe_nom",
            "module_nom",
            "semestre_nom",
            "name",
        ]


class AffectationSerializer(serializers.ModelSerializer):
    enseignant_nom = serializers.CharField(source="enseignant.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)

    class Meta:
        model = Affectation
        fields = [
            "id",
            "enseignant",
            "enseignant_nom",
            "module",
            "module_nom",
            "classe",
            "classe_nom",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "enseignant_nom", "module_nom", "classe_nom"]


class AcademicInscriptionSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    annee_academique_libelle = serializers.CharField(source="annee_academique_ref.libelle", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)
    filiere_nom = serializers.CharField(source="niveau.cycle.filiere.nom", read_only=True)

    class Meta:
        model = Inscription
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "classe",
            "classe_nom",
            "niveau",
            "niveau_nom",
            "filiere_nom",
            "annee_academique",
            "annee_academique_ref",
            "annee_academique_libelle",
            "date_inscription",
        ]


class AcademicNoteSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    evaluation_nom = serializers.CharField(source="evaluation.libelle", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    session = serializers.CharField(required=False, allow_blank=True)
    annee_academique = serializers.CharField(required=False, allow_blank=True)
    formateur_nom = serializers.SerializerMethodField()

    def get_formateur_nom(self, obj):
        if not obj.module_id or not obj.classe_id:
            return "Non assigné"
        from academique.models import Affectation
        aff = Affectation.objects.filter(module_id=obj.module_id, classe_id=obj.classe_id).first()
        return aff.enseignant.nom if aff and aff.enseignant else "Non assigné"

    def _validate_note(self, value):
        if value is not None and value > 20:
            raise serializers.ValidationError("La note ne peut pas dépasser 20.")
        if value is not None and value < 0:
            raise serializers.ValidationError("La note ne peut pas être négative.")
        return value

    def validate_note_cc(self, value):
        return self._validate_note(value)

    def validate_note_sn(self, value):
        return self._validate_note(value)

    def validate_note_rattrapage(self, value):
        return self._validate_note(value)

    class Meta:
        model = Note
        fields = "__all__"


class FraisSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)

    class Meta:
        model = Frais
        fields = "__all__"


class AcademicPaiementSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    frais_libelle = serializers.CharField(source="frais.libelle", read_only=True)
    classe_nom = serializers.CharField(source="frais.classe.nom", read_only=True)

    class Meta:
        model = Paiement
        fields = "__all__"


class AcademicEmploiDuTempsSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    formateur_nom = serializers.CharField(source="formateur.nom", read_only=True)
    salle_nom = serializers.CharField(source="salle.nom", read_only=True)

    class Meta:
        model = EmploiDuTemps
        fields = "__all__"


class PreInscriptionSerializer(serializers.ModelSerializer):
    filiere_souhaitee_nom = serializers.CharField(source="filiere_souhaitee.nom", read_only=True)
    cycle_souhaite_nom = serializers.CharField(source="cycle_souhaite.nom", read_only=True)
    niveau_souhaite_nom = serializers.CharField(source="niveau_souhaite.nom", read_only=True)
    name = serializers.CharField(read_only=True)

    class Meta:
        model = PreInscription
        fields = [
            "id",
            "name",
            "description",
            "nom_candidat",
            "prenom_candidat",
            "email",
            "telephone",
            "filiere_souhaitee",
            "filiere_souhaitee_nom",
            "cycle_souhaite",
            "cycle_souhaite_nom",
            "niveau_souhaite",
            "niveau_souhaite_nom",
            "statut",
            "bulletin",
            "message",
            "nom_parent",
            "whatsapp_parent",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "created_at",
            "updated_at",
            "filiere_souhaitee_nom",
            "cycle_souhaite_nom",
            "niveau_souhaite_nom",
        ]

    def validate_email(self, value):
        if not self.instance:
            if Etudiant.objects.filter(email__iexact=value).exists():
                raise serializers.ValidationError(
                    "Un étudiant avec cet email est déjà inscrit."
                )
            existing = PreInscription.objects.filter(
                email__iexact=value,
                statut="EN_ATTENTE",
            ).exists()
            if existing:
                raise serializers.ValidationError(
                    "Une pré-inscription avec cet email est déjà en cours de traitement. "
                    "Veuillez patienter pendant le traitement de votre dossier."
                )
        return value

    def validate_telephone(self, value):
        if not self.instance:
            if Etudiant.objects.filter(contact=value).exists():
                raise serializers.ValidationError(
                    "Un étudiant avec ce numéro de téléphone est déjà inscrit."
                )
            existing = PreInscription.objects.filter(
                telephone=value,
                statut="EN_ATTENTE",
            ).exists()
            if existing:
                raise serializers.ValidationError(
                    "Une pré-inscription avec ce numéro de téléphone est déjà en cours de traitement. "
                    "Veuillez patienter pendant le traitement de votre dossier."
                )
        return value


class EpreuveSerializer(serializers.ModelSerializer):
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    annee_academique_libelle = serializers.CharField(source="annee_academique.libelle", read_only=True)
    semestre_nom = serializers.CharField(source="semestre.nom", read_only=True, allow_null=True)

    class Meta:
        model = Epreuve
        fields = [
            "id",
            "nom",
            "description",
            "filiere",
            "filiere_nom",
            "niveau",
            "niveau_nom",
            "module",
            "module_nom",
            "annee_academique",
            "annee_academique_libelle",
            "semestre",
            "semestre_nom",
            "type_epreuve",
            "fichier",
            "corrige",
            "auteur",
            "est_partage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "filiere_nom",
            "niveau_nom",
            "module_nom",
            "annee_academique_libelle",
            "semestre_nom",
        ]

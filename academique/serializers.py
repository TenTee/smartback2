from rest_framework import serializers

from emploidutemps.models import EmploiDuTemps
from etudiants.models import Inscription
from formations.models import Niveau
from modules.models import Module
from notes.models import Note
from paiements.models import Frais, Paiement
from formations.models import Formation

from .models import (
    Affectation,
    AnneeAcademique,
    Classe,
    Cycle,
    Domaine,
    Evaluation,
    Faculte,
    Filiere,
    PreInscription,
    Semestre,
    Specialite,
)


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


class FaculteSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Faculte
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

    def validate_nom(self, value):
        value = value.strip()
        qs = Faculte.objects.filter(nom__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Une faculté avec ce nom existe déjà.")
        return value


class DomaineSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Domaine
    parent_field = "faculte"
    faculte_nom = serializers.CharField(source="faculte.nom", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Domaine
        fields = [
            "id",
            "faculte",
            "faculte_nom",
            "nom",
            "name",
            "code",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "faculte_nom", "name"]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)


class FiliereSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Filiere
    parent_field = "domaine"
    domaine_nom = serializers.CharField(source="domaine.nom", read_only=True)
    faculte_nom = serializers.CharField(source="domaine.faculte.nom", read_only=True)
    formation_nom = serializers.CharField(source="formation.intitule", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Filiere
        fields = [
            "id",
            "domaine",
            "domaine_nom",
            "faculte_nom",
            "formation",
            "formation_nom",
            "nom",
            "name",
            "code",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "domaine_nom",
            "faculte_nom",
            "formation_nom",
            "name",
        ]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)


class SpecialiteSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Specialite
    parent_field = "filiere"
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    domaine_nom = serializers.CharField(source="filiere.domaine.nom", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Specialite
        fields = [
            "id",
            "filiere",
            "filiere_nom",
            "domaine_nom",
            "nom",
            "name",
            "code",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "filiere_nom",
            "domaine_nom",
            "name",
        ]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)


class CycleSerializer(CaseInsensitiveUniqueWithinParentMixin, serializers.ModelSerializer):
    model_class = Cycle
    parent_field = "specialite"
    specialite_nom = serializers.CharField(source="specialite.nom", read_only=True)
    filiere_nom = serializers.CharField(source="specialite.filiere.nom", read_only=True)
    levels_count = serializers.SerializerMethodField()
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Cycle
        fields = [
            "id",
            "specialite",
            "specialite_nom",
            "filiere_nom",
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
            "specialite_nom",
            "filiere_nom",
            "levels_count",
            "name",
        ]

    def validate(self, attrs):
        return self.validate_scoped_name(attrs)

    def get_levels_count(self, obj):
        return obj.niveaux.count()


class LevelSerializer(serializers.ModelSerializer):
    cycle_nom = serializers.CharField(source="cycle.nom", read_only=True)
    specialite_id = serializers.IntegerField(source="cycle.specialite_id", read_only=True)
    specialite_nom = serializers.CharField(source="cycle.specialite.nom", read_only=True)
    filiere_id = serializers.IntegerField(source="formation_id", read_only=True)
    filiere_nom = serializers.CharField(source="formation.intitule", read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Niveau
        fields = [
            "id",
            "formation",
            "filiere_id",
            "filiere_nom",
            "cycle",
            "cycle_nom",
            "specialite_id",
            "specialite_nom",
            "nom",
            "name",
            "modules",
        ]
        read_only_fields = [
            "id",
            "filiere_id",
            "filiere_nom",
            "cycle_nom",
            "specialite_id",
            "specialite_nom",
            "name",
        ]

    def validate_nom(self, value):
        return value.strip()

    def validate(self, attrs):
        formation = attrs.get("formation") or getattr(self.instance, "formation", None)
        cycle = attrs.get("cycle") or getattr(self.instance, "cycle", None)
        nom = attrs.get("nom") or getattr(self.instance, "nom", None)

        if formation and cycle:
            filiere = getattr(cycle.specialite, "filiere", None)
            if filiere and filiere.formation_id and filiere.formation_id != formation.id:
                raise serializers.ValidationError({
                    "formation": "Le niveau doit utiliser la formation liée à la filière de cette spécialité.",
                })

        queryset = Niveau.objects.filter(formation=formation, nom__iexact=nom.strip())
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if formation and nom and queryset.exists():
            raise serializers.ValidationError({
                "nom": "Un niveau avec ce nom existe déjà dans cette filière.",
            })
        return attrs


class CourseSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="nom", read_only=True)
    formation = serializers.PrimaryKeyRelatedField(queryset=Formation.objects.all(), write_only=True, required=False)
    formations = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id",
            "nom",
            "name",
            "duree",
            "coefficient",
            "has_tp",
            "pourcentage_cc",
            "pourcentage_sn",
            "pourcentage_tp",
            "semestre",
            "formation",
            "formations",
        ]
        read_only_fields = ["id", "name"]

    def validate_nom(self, value):
        value = value.strip()
        qs = Module.objects.filter(nom__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Un cours avec ce nom existe déjà.")
        return value

    def get_formations(self, obj):
        return [
            {
                "id": formation.id,
                "intitule": formation.intitule,
            }
            for formation in obj.formations.all()
        ]

    def create(self, validated_data):
        formation = validated_data.pop("formation", None)
        module = Module.objects.create(**validated_data)
        if formation is not None:
            formation.modules.add(module)
        return module

    def update(self, instance, validated_data):
        formation = validated_data.pop("formation", None)
        module = super().update(instance, validated_data)
        if formation is not None:
            formation.modules.add(module)
        return module

    def validate(self, attrs):
        has_tp = attrs.get("has_tp", getattr(self.instance, "has_tp", False))
        pourcentage_cc = attrs.get("pourcentage_cc", getattr(self.instance, "pourcentage_cc", 0)) or 0
        pourcentage_sn = attrs.get("pourcentage_sn", getattr(self.instance, "pourcentage_sn", 0)) or 0
        pourcentage_tp = attrs.get("pourcentage_tp", getattr(self.instance, "pourcentage_tp", 0)) or 0

        total = pourcentage_cc + pourcentage_sn + (pourcentage_tp if has_tp else 0)
        if total != 100:
            raise serializers.ValidationError(
                "La somme des pourcentages doit être égale à 100."
            )
        if not has_tp and pourcentage_tp:
            raise serializers.ValidationError({
                "pourcentage_tp": "Le pourcentage TP doit être à 0 quand has_tp est faux.",
            })
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

    def validate(self, attrs):
        date_debut = attrs.get("date_debut", getattr(self.instance, "date_debut", None))
        date_fin = attrs.get("date_fin", getattr(self.instance, "date_fin", None))
        est_active = attrs.get("est_active", getattr(self.instance, "est_active", False))

        if date_debut and date_fin and date_debut >= date_fin:
            raise serializers.ValidationError({
                "date_fin": "La date de fin doit être postérieure à la date de début.",
            })

        if est_active:
            qs = AnneeAcademique.objects.filter(est_active=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    "est_active": "Une seule année académique peut être active à la fois.",
                })
        return attrs


class ClasseSerializer(serializers.ModelSerializer):
    specialite_nom = serializers.CharField(source="specialite.nom", read_only=True)
    cycle_nom = serializers.CharField(source="cycle.nom", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)
    annee_academique_libelle = serializers.CharField(source="annee_academique.libelle", read_only=True)
    modules_details = CourseSerializer(source="modules", many=True, read_only=True)
    name = serializers.CharField(source="nom", read_only=True)

    class Meta:
        model = Classe
        fields = [
            "id",
            "specialite",
            "specialite_nom",
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
            "modules_details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "nom",
            "name",
            "created_at",
            "updated_at",
            "specialite_nom",
            "cycle_nom",
            "niveau_nom",
            "annee_academique_libelle",
            "modules_details",
        ]

    def validate(self, attrs):
        specialite = attrs.get("specialite") or getattr(self.instance, "specialite", None)
        cycle = attrs.get("cycle") or getattr(self.instance, "cycle", None)
        niveau = attrs.get("niveau") or getattr(self.instance, "niveau", None)
        modules = attrs.get("modules")

        if cycle and specialite and cycle.specialite_id != specialite.id:
            raise serializers.ValidationError({
                "cycle": "Le cycle doit appartenir à la spécialité sélectionnée.",
            })

        if niveau and cycle and niveau.cycle_id and niveau.cycle_id != cycle.id:
            raise serializers.ValidationError({
                "niveau": "Le niveau doit appartenir au cycle sélectionné.",
            })

        if modules and niveau:
            allowed_module_ids = set(niveau.modules.values_list("id", flat=True))
            if not allowed_module_ids:
                allowed_module_ids = set(niveau.formation.modules.values_list("id", flat=True))
            invalid_ids = [module.id for module in modules if module.id not in allowed_module_ids]
            if invalid_ids:
                raise serializers.ValidationError({
                    "modules": f"Les modules {invalid_ids} ne sont pas autorisés pour ce niveau.",
                })
        return attrs


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

    def validate(self, attrs):
        classe = attrs.get("classe") or getattr(self.instance, "classe", None)
        module = attrs.get("module") or getattr(self.instance, "module", None)
        semestre = attrs.get("semestre") or getattr(self.instance, "semestre", None)

        if classe and module and not classe.modules.filter(pk=module.pk).exists():
            raise serializers.ValidationError({
                "module": "Le module doit déjà être rattaché à la classe.",
            })

        if semestre and classe and semestre.annee_academique_id != classe.annee_academique_id:
            raise serializers.ValidationError({
                "semestre": "Le semestre doit appartenir à la même année académique que la classe.",
            })
        return attrs


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

    def validate(self, attrs):
        classe = attrs.get("classe") or getattr(self.instance, "classe", None)
        module = attrs.get("module") or getattr(self.instance, "module", None)
        if classe and module and not classe.modules.filter(pk=module.pk).exists():
            raise serializers.ValidationError({
                "module": "Le module affecté doit appartenir à la classe.",
            })
        return attrs


class AcademicInscriptionSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    annee_academique_libelle = serializers.CharField(source="annee_academique_ref.libelle", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)

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
    module_semestre = serializers.CharField(source="module.semestre", read_only=True)

    class Meta:
        model = Note
        fields = "__all__"
        extra_kwargs = {
            "session": {"required": False},
        }


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

    class Meta:
        model = EmploiDuTemps
        fields = "__all__"


class PreInscriptionSerializer(serializers.ModelSerializer):
    filiere_souhaitee_nom = serializers.CharField(source="filiere_souhaitee.nom", read_only=True)
    formation_souhaitee_nom = serializers.CharField(source="formation_souhaitee.intitule", read_only=True)
    niveau_souhaite_nom = serializers.CharField(source="niveau_souhaite.nom", read_only=True)
    name = serializers.CharField(read_only=True)
    montant_inscription_verse = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        write_only=True,
        required=False,
        min_value=0,
    )
    montant_formation_verse = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        write_only=True,
        required=False,
        min_value=0,
    )

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
            "formation_souhaitee",
            "filiere_souhaitee_nom",
            "formation_souhaitee_nom",
            "niveau_souhaite",
            "niveau_souhaite_nom",
            "statut",
            "montant_inscription_verse",
            "montant_formation_verse",
            "bulletin",
            "message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "created_at",
            "updated_at",
            "filiere_souhaitee_nom",
            "formation_souhaitee_nom",
            "niveau_souhaite_nom",
        ]

    def validate(self, attrs):
        filiere = attrs.get("filiere_souhaitee") or getattr(self.instance, "filiere_souhaitee", None)
        formation = attrs.get("formation_souhaitee") or getattr(self.instance, "formation_souhaitee", None)
        niveau = attrs.get("niveau_souhaite") or getattr(self.instance, "niveau_souhaite", None)

        if filiere and formation and filiere.formation_id != formation.id:
            raise serializers.ValidationError({
                "formation_souhaitee": "La formation souhaitée doit correspondre à la filière choisie.",
            })

        if niveau and formation and niveau.formation_id != formation.id:
            raise serializers.ValidationError({
                "niveau_souhaite": "Le niveau souhaité n'appartient pas à la formation choisie.",
            })

        if filiere and niveau and filiere.formation_id and niveau.formation_id != filiere.formation_id:
            raise serializers.ValidationError({
                "niveau_souhaite": "Le niveau souhaité n'appartient pas à la filière choisie.",
            })

        return attrs

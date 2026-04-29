# etudiants/serializers.py
from rest_framework import serializers
from .models import Etudiant, EtudiantDocument, Inscription
from academique.models import Filiere, Cycle, Niveau, Classe, AnneeAcademique
from academique.serializers import FiliereSerializer, LevelSerializer

# --- Documents liés aux étudiants ---
class EtudiantDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EtudiantDocument
        fields = ["id", "type_document", "fichier", "date_upload"]


# --- Inscriptions ---
class InscriptionSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    niveau_nom = serializers.CharField(source='niveau.nom', read_only=True)
    filiere_nom = serializers.CharField(source='niveau.cycle.filiere.nom', read_only=True)
    cycle_id = serializers.IntegerField(source="niveau.cycle_id", read_only=True)
    cycle_nom = serializers.CharField(source="niveau.cycle.nom", read_only=True)
    annee_academique_ref_libelle = serializers.CharField(source='annee_academique_ref.libelle', read_only=True)

    class Meta:
        model = Inscription
        fields = [
            'id',
            'etudiant',
            'classe',
            'classe_nom',
            'niveau',
            'niveau_nom',
            'filiere_nom',
            'cycle_id',
            'cycle_nom',
            'annee_academique',
            'annee_academique_ref',
            'annee_academique_ref_libelle',
            'date_inscription',
        ]


# --- Étudiant ---
class EtudiantSerializer(serializers.ModelSerializer):
    # Lecture
    filiere_details = FiliereSerializer(source="filiere", read_only=True)
    
    # Écriture
    filiere_id = serializers.PrimaryKeyRelatedField(
        queryset=Filiere.objects.all(),
        source="filiere",
        write_only=True
    )
    cycle_id = serializers.PrimaryKeyRelatedField(
        queryset=Cycle.objects.all(),
        write_only=True,
        required=False,
    )
    niveau_id = serializers.IntegerField(write_only=True, required=False)
    classe_id = serializers.IntegerField(write_only=True, required=False)
    annee_academique_ref_id = serializers.IntegerField(write_only=True, required=False)

    # Lecture seule
    documents = EtudiantDocumentSerializer(many=True, read_only=True)
    inscriptions = InscriptionSerializer(many=True, read_only=True)

    class Meta:
        model = Etudiant
        fields = [
            "id",
            "matricule",
            "nom",
            "date_naissance",
            "contact",
            "email",
            "filiere_details",
            "filiere_id",
            "cycle_id",
            "niveau_id",
            "classe_id",
            "annee_academique_ref_id",
            "statut",
            "documents",
            "inscriptions",
        ]

    def create(self, validated_data):
        cycle = validated_data.pop('cycle_id', None)
        niveau_id = validated_data.pop('niveau_id', None)
        classe_id = validated_data.pop('classe_id', None)
        annee_academique_ref_id = validated_data.pop('annee_academique_ref_id', None)

        etudiant = super().create(validated_data)

        if classe_id:
            try:
                classe = Classe.objects.get(pk=classe_id)
                annee = classe.annee_academique
                if annee_academique_ref_id:
                    annee = AnneeAcademique.objects.get(pk=annee_academique_ref_id)
                Inscription.objects.create(
                    etudiant=etudiant,
                    classe=classe,
                    niveau=classe.niveau,
                    annee_academique=annee.libelle,
                    annee_academique_ref=annee,
                )
            except (Classe.DoesNotExist, AnneeAcademique.DoesNotExist):
                pass
        elif niveau_id:
            try:
                niveau = Niveau.objects.get(pk=niveau_id)
                annee = AnneeAcademique.objects.filter(est_active=True).first()
                Inscription.objects.create(
                    etudiant=etudiant,
                    niveau=niveau,
                    annee_academique=annee.libelle if annee else "2024-2025",
                    annee_academique_ref=annee
                )
            except Niveau.DoesNotExist:
                pass
        
        return etudiant

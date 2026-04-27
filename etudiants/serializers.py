# etudiants/serializers.py
from rest_framework import serializers
from .models import Etudiant, EtudiantDocument, Inscription
from formations.models import Formation

# --- Formation ---
class FormationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Formation
        fields = ["id", "intitule"]  # on expose seulement ce qui est utile


# --- Documents liés aux étudiants ---
class EtudiantDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EtudiantDocument
        fields = ["id", "type_document", "fichier", "date_upload"]


# --- Inscriptions ---
class InscriptionSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    niveau_nom = serializers.CharField(source='niveau.nom', read_only=True)
    formation_nom = serializers.CharField(source='niveau.formation.intitule', read_only=True)
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
            'formation_nom',
            'annee_academique',
            'annee_academique_ref',
            'annee_academique_ref_libelle',
            'date_inscription',
        ]


# --- Étudiant ---
class EtudiantSerializer(serializers.ModelSerializer):
    # Lecture : renvoie l'objet complet {id, intitule}
    filiere = FormationSerializer(read_only=True)

    # Écriture : permet d'envoyer juste l'ID
    filiere_id = serializers.PrimaryKeyRelatedField(
        queryset=Formation.objects.all(),
        source="filiere",
        write_only=True
    )

    # ✅ Nouveau champ pour l'inscription initiale (niveau)
    niveau_id = serializers.IntegerField(write_only=True, required=False)
    classe_id = serializers.IntegerField(write_only=True, required=False)
    annee_academique_ref_id = serializers.IntegerField(write_only=True, required=False)

    # ✅ Lecture seule des documents liés
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
            "filiere",      # lecture : objet {id, intitule}
            "filiere_id",   # écriture : juste l’ID
            "niveau_id",    # écriture : pour inscription initiale
            "classe_id",
            "annee_academique_ref_id",
            "statut",       # ajout statut (lecture/ecriture selon besoins, read-only par défaut car géré par endpoint via frontend si besoin ou via la création si géré)
            "documents",    # lecture seule : liste des fichiers liés
            "inscriptions", # historique des inscriptions
        ]

    def create(self, validated_data):
        niveau_id = validated_data.pop('niveau_id', None)
        classe_id = validated_data.pop('classe_id', None)
        annee_academique_ref_id = validated_data.pop('annee_academique_ref_id', None)
        etudiant = super().create(validated_data)

        if classe_id:
            try:
                from academique.models import Classe, AnneeAcademique
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
                from formations.models import Niveau
                niveau = Niveau.objects.get(pk=niveau_id)
                Inscription.objects.create(
                    etudiant=etudiant,
                    niveau=niveau,
                    annee_academique="2024-2025" # À dynamiser plus tard ou passer en paramètre
                )
            except Niveau.DoesNotExist:
                pass # ou lever une erreur
        
        return etudiant

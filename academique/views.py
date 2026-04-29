import io
import traceback
from decimal import Decimal

import openpyxl
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from openpyxl.styles import Font
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from emploidutemps.models import EmploiDuTemps
from etudiants.models import Etudiant, Inscription
from modules.models import Module
from notes.models import Note
from paiements.models import Frais, Paiement

from .models import (
    Affectation,
    AnneeAcademique,
    Classe,
    Cycle,
    Departement,
    Evaluation,
    Filiere,
    Niveau,
    ParametresGlobaux,
    PreInscription,
    Semestre,
    UniversiteTutelle,
)
from .serializers import (
    AcademicEmploiDuTempsSerializer,
    AcademicInscriptionSerializer,
    AcademicNoteSerializer,
    AcademicPaiementSerializer,
    AffectationSerializer,
    AnneeAcademiqueSerializer,
    ClasseSerializer,
    CourseSerializer,
    CycleSerializer,
    DepartementSerializer,
    EvaluationSerializer,
    FiliereSerializer,
    FraisSerializer,
    LevelSerializer,
    ParametresGlobauxSerializer,
    PreInscriptionSerializer,
    SemestreSerializer,
    UniversiteTutelleSerializer,
)


class OptimizedModelViewSet(viewsets.ModelViewSet):
    search_fields = ()
    ordering_fields = "__all__"


class ParametresGlobauxViewSet(viewsets.ModelViewSet):
    """
    ViewSet to manage ParametresGlobaux. 
    Since it's a singleton, list returns a single object and create is limited.
    """
    queryset = ParametresGlobaux.objects.all()
    serializer_class = ParametresGlobauxSerializer

    def get_queryset(self):
        # Assure qu'on retourne au moins un objet s'il n'y en a pas
        ParametresGlobaux.get_parametres()
        return ParametresGlobaux.objects.all()


class UniversiteTutelleViewSet(OptimizedModelViewSet):
    queryset = UniversiteTutelle.objects.all()
    serializer_class = UniversiteTutelleSerializer
    search_fields = ("nom", "code", "description")
    ordering = ("nom",)


class DepartementViewSet(OptimizedModelViewSet):
    queryset = Departement.objects.select_related("universite_tutelle").all()
    serializer_class = DepartementSerializer
    filterset_fields = ("universite_tutelle",)
    search_fields = ("nom", "code", "description", "universite_tutelle__nom")
    ordering = ("universite_tutelle__nom", "nom")


class FiliereViewSet(OptimizedModelViewSet):
    queryset = Filiere.objects.select_related("departement", "departement__universite_tutelle").all()
    serializer_class = FiliereSerializer
    filterset_fields = ("departement",)
    search_fields = ("nom", "code", "description", "departement__nom")
    ordering = ("departement__nom", "nom")

    @action(detail=True, methods=["get"], url_path="cycles")
    def cycles(self, request, pk=None):
        cycles = Cycle.objects.filter(filiere=self.get_object())
        serializer = CycleSerializer(cycles, many=True)
        return Response(serializer.data)


class CycleViewSet(OptimizedModelViewSet):
    queryset = Cycle.objects.select_related("filiere").prefetch_related("niveaux").all()
    serializer_class = CycleSerializer
    filterset_fields = ("filiere",)
    search_fields = ("nom", "code", "description", "filiere__nom")
    ordering = ("filiere__nom", "ordre", "nom")

    @action(detail=True, methods=["get"], url_path="levels")
    def levels(self, request, pk=None):
        serializer = LevelSerializer(self.get_object().niveaux.all(), many=True)
        return Response(serializer.data)


class LevelViewSet(OptimizedModelViewSet):
    queryset = Niveau.objects.select_related("cycle", "cycle__filiere").prefetch_related("modules").all()
    serializer_class = LevelSerializer
    filterset_fields = ("cycle", "cycle__filiere")
    search_fields = ("nom", "cycle__nom", "cycle__filiere__nom")
    ordering = ("cycle__filiere__nom", "nom")


class CourseViewSet(OptimizedModelViewSet):
    queryset = Module.objects.all()
    serializer_class = CourseSerializer
    search_fields = ("nom",)
    ordering = ("nom",)


class AnneeAcademiqueViewSet(OptimizedModelViewSet):
    queryset = AnneeAcademique.objects.all()
    serializer_class = AnneeAcademiqueSerializer
    filterset_fields = ("est_active",)
    search_fields = ("libelle", "description")
    ordering = ("-libelle",)


class ClasseViewSet(OptimizedModelViewSet):
    queryset = (
        Classe.objects.select_related(
            "filiere",
            "cycle",
            "niveau",
            "annee_academique",
        )
        .prefetch_related("modules")
        .all()
    )
    serializer_class = ClasseSerializer
    filterset_fields = ("filiere", "cycle", "niveau", "annee_academique")
    search_fields = (
        "nom",
        "description",
        "filiere__nom",
        "cycle__nom",
        "niveau__nom",
        "annee_academique__libelle",
    )
    ordering = ("annee_academique__libelle", "nom")


class SemestreViewSet(OptimizedModelViewSet):
    queryset = Semestre.objects.select_related("annee_academique").all()
    serializer_class = SemestreSerializer
    filterset_fields = ("annee_academique", "ordre")
    search_fields = ("nom", "description", "annee_academique__libelle")
    ordering = ("annee_academique__libelle", "ordre")


class EvaluationViewSet(OptimizedModelViewSet):
    queryset = Evaluation.objects.select_related("classe", "module", "semestre").all()
    serializer_class = EvaluationSerializer
    filterset_fields = ("classe", "module", "semestre", "type_evaluation")
    search_fields = ("libelle", "description", "classe__nom", "module__nom")
    ordering = ("-date_evaluation", "libelle")


class AffectationViewSet(OptimizedModelViewSet):
    queryset = Affectation.objects.select_related("enseignant", "module", "classe").all()
    serializer_class = AffectationSerializer
    filterset_fields = ("enseignant", "module", "classe")
    search_fields = ("enseignant__nom", "module__nom", "classe__nom")
    ordering = ("classe__nom", "module__nom")


class AcademicInscriptionViewSet(OptimizedModelViewSet):
    queryset = Inscription.objects.select_related("etudiant", "classe", "niveau", "annee_academique_ref").all()
    serializer_class = AcademicInscriptionSerializer
    filterset_fields = ("classe", "niveau", "annee_academique_ref")
    search_fields = ("etudiant__nom", "classe__nom", "niveau__nom", "annee_academique")
    ordering = ("-date_inscription",)


class AcademicNoteViewSet(OptimizedModelViewSet):
    queryset = Note.objects.select_related("etudiant", "evaluation", "classe", "module").all()
    serializer_class = AcademicNoteSerializer
    filterset_fields = ("module", "classe", "evaluation")
    search_fields = ("etudiant__nom", "module__nom", "classe__nom")
    ordering = ("etudiant__nom",)


class FraisViewSet(OptimizedModelViewSet):
    queryset = Frais.objects.select_related("classe").all()
    serializer_class = FraisSerializer


class AcademicPaiementViewSet(OptimizedModelViewSet):
    queryset = Paiement.objects.select_related("etudiant", "filiere", "frais", "frais__classe").all()
    serializer_class = AcademicPaiementSerializer


class AcademicEmploiDuTempsViewSet(OptimizedModelViewSet):
    queryset = EmploiDuTemps.objects.select_related("classe", "filiere", "niveau", "module", "formateur").all()
    serializer_class = AcademicEmploiDuTempsSerializer


class PreInscriptionViewSet(OptimizedModelViewSet):
    queryset = PreInscription.objects.select_related("filiere_souhaitee", "cycle_souhaite", "niveau_souhaite").all()
    serializer_class = PreInscriptionSerializer
    filterset_fields = ("statut", "filiere_souhaitee", "cycle_souhaite", "niveau_souhaite")
    search_fields = ("nom_candidat", "prenom_candidat", "email", "telephone")
    ordering = ("-created_at",)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        preinscription = self.get_object()
        try:
            with transaction.atomic():
                preinscription.statut = "APPROUVEE"
                preinscription.save(update_fields=["statut", "updated_at"])
                
                # Extraire les montants payés à l'inscription et la classe choisie
                montant_inscription = request.data.get("montant_inscription_verse", "0")
                montant_formation = request.data.get("montant_formation_verse", "0")
                classe_id = request.data.get("classe_id")
                
                self._create_etudiant_and_inscription(
                    preinscription, 
                    montant_inscription=Decimal(montant_inscription),
                    montant_formation=Decimal(montant_formation),
                    classe_id=classe_id
                )
            return Response({"message": "Pré-inscription approuvée et étudiant créé."})
        except Exception as e:
            traceback.print_exc()
            return Response(
                {"error": str(e), "traceback": traceback.format_exc()},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        preinscription = self.get_object()
        preinscription.statut = "REJETEE"
        preinscription.save(update_fields=["statut", "updated_at"])
        return Response({"message": "Pré-inscription rejetée."})

    def _create_etudiant_and_inscription(self, preinscription, montant_inscription=0, montant_formation=0, classe_id=None):
        if not preinscription.filiere_souhaitee_id:
            raise ValidationError("La filière souhaitée est obligatoire pour approuver l'inscription.")

        annee = AnneeAcademique.objects.filter(est_active=True).order_by("-libelle").first()
        annee_libelle = annee.libelle if annee else str(timezone.now().year)

        # 1. Créer ou récupérer l'étudiant
        etudiant, created = Etudiant.objects.get_or_create(
            email=preinscription.email,
            defaults={
                "nom": f"{preinscription.nom_candidat} {preinscription.prenom_candidat}".strip(),
                "contact": preinscription.telephone,
                "filiere": preinscription.filiere_souhaitee,
                "statut": "Inscrit",
            },
        )

        # 2. Créer l'inscription si un niveau est souhaité
        inscription = None
        if preinscription.niveau_souhaite_id:
            # Recherche automatique de la classe correspondante pour l'année active
            classe_auto = None
            if not classe_id:
                from academique.models import Classe
                classe_auto = Classe.objects.filter(
                    filiere=preinscription.filiere_souhaitee,
                    niveau=preinscription.niveau_souhaite,
                    annee_academique=annee
                ).first()
            
            inscription, _ = Inscription.objects.get_or_create(
                etudiant=etudiant,
                niveau=preinscription.niveau_souhaite,
                annee_academique=annee_libelle,
                defaults={"annee_academique_ref": annee, "classe_id": classe_id or (classe_auto.id if classe_auto else None)},
            )
            # Si déjà existante mais classe_id passée ou détectée, on met à jour
            final_classe_id = classe_id or (classe_auto.id if classe_auto else None)
            if inscription and final_classe_id and not inscription.classe_id:
                inscription.classe_id = final_classe_id
                inscription.save()

        # 3. Gérer les paiements initiaux
        if inscription and inscription.classe:
            from paiements.models import Frais, Paiement
            
            # Paiement des frais d'inscription
            if montant_inscription > 0:
                frais_ins = Frais.objects.filter(
                    classe=inscription.classe, 
                    libelle__icontains="inscription"
                ).first()
                if frais_ins:
                    Paiement.objects.create(
                        etudiant=etudiant,
                        frais=frais_ins,
                        paiement_type="INSCRIPTION",
                        montant_paye=montant_inscription,
                        moyen_paiement="cash" # Par défaut
                    )

            # Paiement (avance) sur frais de formation
            if montant_formation > 0:
                # On cherche la première tranche (souvent "Scolarité" ou "Tranche 1")
                frais_form = Frais.objects.filter(
                    classe=inscription.classe
                ).exclude(libelle__icontains="inscription").order_by("id").first()
                
                if frais_form:
                    Paiement.objects.create(
                        etudiant=etudiant,
                        frais=frais_form,
                        paiement_type="FORMATION",
                        montant_paye=montant_formation,
                        moyen_paiement="cash"
                    )

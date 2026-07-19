import io
import traceback
from decimal import Decimal

import openpyxl
from django.db import transaction
from django.http import HttpResponse, FileResponse
from django.conf import settings
import os
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from openpyxl.styles import Font
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from emploidutemps.models import EmploiDuTemps
from etudiants.models import Etudiant, Inscription
from modules.models import Module
from notes.models import Note
from paiements.models import Frais, Paiement
from .middleware import get_current_academic_year_id

from .models import (
    Affectation,
    AnneeAcademique,
    Classe,
    ConfigurationEtablissement,
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
from .serializers import (
    AcademicEmploiDuTempsSerializer,
    AcademicInscriptionSerializer,
    AcademicNoteSerializer,
    AcademicPaiementSerializer,
    AffectationSerializer,
    AnneeAcademiqueSerializer,
    ClasseSerializer,
    ConfigurationEtablissementSerializer,
    CourseSerializer,
    CycleSerializer,
    CycleGlobalSerializer,
    DepartementSerializer,
    EpreuveSerializer,
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

    def get_queryset(self):
        queryset = super().get_queryset()

        # Ne pas filtrer par année académique pour les actions destructrices/modificatrices
        # afin d'éviter les 404 sur des objets existants mais d'une autre année
        if self.action in ('destroy', 'retrieve', 'update', 'partial_update', 'reject', 'approve'):
            return queryset

        year_id = get_current_academic_year_id()

        if not year_id:
            return queryset

        # Mapping des champs pour filtrer par année académique selon le modèle
        model = self.queryset.model
        model_name = model.__name__

        # 1. Filtre direct
        if hasattr(model, 'annee_academique_id') and not model_name == "Inscription":
            queryset = queryset.filter(annee_academique_id=year_id)
        elif hasattr(model, 'annee_academique_ref_id'):
            queryset = queryset.filter(annee_academique_ref_id=year_id)

        # 2. Filtre via relation (Classe)
        elif hasattr(model, 'classe_id'):
            queryset = queryset.filter(classe__annee_academique_id=year_id)

        # 3. Cas spécifiques (Paiement)
        elif model_name == "Paiement":
            queryset = queryset.filter(frais__classe__annee_academique_id=year_id)

        return queryset


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


class ConfigurationEtablissementViewSet(viewsets.ModelViewSet):
    queryset = ConfigurationEtablissement.objects.all()
    serializer_class = ConfigurationEtablissementSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'current']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        # Assure qu'on retourne au moins un objet
        ConfigurationEtablissement.get_config()
        return ConfigurationEtablissement.objects.all()

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        config = ConfigurationEtablissement.get_config()
        serializer = self.get_serializer(config)
        return Response(serializer.data)


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

    def get_permissions(self):
        # Allow public access to list/retrieve filieres and the nested cycles action
        if self.action in ["list", "retrieve", "cycles"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        """
        Extended create to optionally accept:
        - `type_cycle`: id of CycleGlobal to create a Cycle for this filière
        - `nombre_niveaux`: integer number of levels to create under the cycle
        - `responsable_nom`: name of the responsible person (stored on Filiere)

        When provided, this will create the Cycle, the requested Nombre de Niveaux
        and for the current academic year will create corresponding Classe objects.
        """
        payload = request.data.copy()
        type_cycle_id = payload.pop("type_cycle", None)
        nombre_niveaux = payload.pop("nombre_niveaux", None)

        with transaction.atomic():
            serializer = self.get_serializer(data=payload)
            serializer.is_valid(raise_exception=True)
            filiere = serializer.save()

            # If a cycle type is provided, create a Cycle and auto-create Niveaux/Classes
            if type_cycle_id:
                try:
                    type_cycle = CycleGlobal.objects.get(pk=type_cycle_id)
                except CycleGlobal.DoesNotExist:
                    raise ValidationError({"type_cycle": "Type de cycle introuvable"})

                # Create the Cycle and name it after the CycleGlobal
                cycle = Cycle.objects.create(filiere=filiere, type_cycle=type_cycle, nom=type_cycle.nom, ordre=1)

                try:
                    levels = int(nombre_niveaux) if nombre_niveaux is not None else 0
                except (ValueError, TypeError):
                    levels = 0

                all_annees = AnneeAcademique.objects.all()

                for i in range(1, levels + 1):
                    niveau_nom = f"{type_cycle.nom} {i}"
                    niveau = Niveau.objects.create(cycle=cycle, nom=niveau_nom, ordre=i)

                    for annee in all_annees:
                        classe_nom = f"{filiere.nom} {type_cycle.nom} {i} ({annee.libelle})"
                        Classe.objects.update_or_create(
                            filiere=filiere,
                            cycle=cycle,
                            niveau=niveau,
                            annee_academique=annee,
                            defaults={"nom": classe_nom}
                        )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["get"], url_path="cycles")
    def cycles(self, request, pk=None):
        cycles = Cycle.objects.filter(filiere=self.get_object())
        serializer = CycleSerializer(cycles, many=True)
        return Response(serializer.data)


class CycleGlobalViewSet(OptimizedModelViewSet):
    queryset = CycleGlobal.objects.all()
    serializer_class = CycleGlobalSerializer
    search_fields = ("nom", "code", "description")
    ordering = ("nom",)


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

    def get_permissions(self):
        # Allow public access to list/retrieve cycles and the nested levels action
        if self.action in ["list", "retrieve", "levels"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


class LevelViewSet(OptimizedModelViewSet):
    queryset = Niveau.objects.select_related("cycle", "cycle__filiere").prefetch_related("modules").all()
    serializer_class = LevelSerializer
    filterset_fields = ("cycle", "cycle__filiere")
    search_fields = ("nom", "cycle__nom", "cycle__filiere__nom")
    ordering = ("cycle__filiere__nom", "nom")

    def get_permissions(self):
        # Allow public access to list/retrieve levels
        if self.action in ["list", "retrieve"]:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]


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

    @action(detail=False, methods=['get'], url_path='saisie-groupee')
    def saisie_groupee(self, request):
        classe_id = request.query_params.get('classe')
        module_id = request.query_params.get('module')
        evaluation_id = request.query_params.get('evaluation')

        if not classe_id or not module_id:
            return Response({"error": "classe and module are required"}, status=400)

        inscriptions = Inscription.objects.filter(classe_id=classe_id).select_related('etudiant')
        
        # Obtenir les notes existantes
        existing_notes = Note.objects.filter(
            classe_id=classe_id, 
            module_id=module_id
        )
        if evaluation_id:
            existing_notes = existing_notes.filter(evaluation_id=evaluation_id)
        else:
            existing_notes = existing_notes.filter(evaluation__isnull=True)
            
        notes_dict = {n.etudiant_id: n for n in existing_notes}

        # Obtenir le formateur pour cette classe/module
        from academique.models import Affectation
        aff = Affectation.objects.filter(classe_id=classe_id, module_id=module_id).first()
        formateur_nom = aff.enseignant.nom if aff and aff.enseignant else "Non assigné"

        data = []
        for ins in inscriptions:
            etudiant = ins.etudiant
            note = notes_dict.get(etudiant.id)
            data.append({
                "etudiant_id": etudiant.id,
                "etudiant_nom": etudiant.nom,
                "etudiant_matricule": etudiant.matricule,
                "classe_id": int(classe_id),
                "module_id": int(module_id),
                "evaluation_id": int(evaluation_id) if evaluation_id else None,
                "formateur_nom": formateur_nom,
                "note_id": note.id if note else None,
                "note_cc": note.note_cc if note else None,
                "note_sn": note.note_sn if note else None,
                "note_rattrapage": note.note_rattrapage if note else None,
                "note_finale": note.note_finale if note else None,
            })
        return Response(data)

    @action(detail=False, methods=['post'], url_path='batch-save')
    def batch_save(self, request):
        try:
            notes_data = request.data.get('notes', [])
            saved_notes = []

            with transaction.atomic():
                for item in notes_data:
                    etudiant_id = item.get('etudiant_id')
                    module_id = item.get('module_id')
                    classe_id = item.get('classe_id')
                    evaluation_id = item.get('evaluation_id')
                    
                    note_cc = item.get('note_cc')
                    note_sn = item.get('note_sn')

                    if not etudiant_id or not module_id:
                        continue

                    # Use filter().first() instead of update_or_create to avoid MultipleObjectsReturned
                    note = Note.objects.filter(
                        etudiant_id=etudiant_id,
                        module_id=module_id,
                        classe_id=classe_id,
                        evaluation_id=evaluation_id,
                    ).first()

                    if note:
                        note.note_cc = note_cc
                        note.note_sn = note_sn
                        note.save()
                    else:
                        note = Note.objects.create(
                            etudiant_id=etudiant_id,
                            module_id=module_id,
                            classe_id=classe_id,
                            evaluation_id=evaluation_id,
                            note_cc=note_cc,
                            note_sn=note_sn,
                        )
                    saved_notes.append(note)

            return Response({
                "message": f"{len(saved_notes)} notes enregistrées",
                "data": AcademicNoteSerializer(saved_notes, many=True).data
            })
        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)


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
    queryset = PreInscription.objects.select_related("filiere_souhaitee", "cycle_souhaite", "niveau_souhaite", "annee_academique").all()
    serializer_class = PreInscriptionSerializer
    filterset_fields = ("statut", "filiere_souhaitee", "cycle_souhaite", "niveau_souhaite")

    def perform_create(self, serializer):
        annee = AnneeAcademique.objects.filter(est_active=True).first()
        serializer.save(annee_academique=annee)

    search_fields = ("nom_candidat", "prenom_candidat", "email", "telephone")
    ordering = ("-created_at",)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        preinscription = self.get_object()
        try:
            with transaction.atomic():
                preinscription.statut = "APPROUVEE"
                preinscription.save()

                if not preinscription.filiere_souhaitee or not preinscription.niveau_souhaite:
                    return Response({"error": "Filière ou niveau manquant sur la pré-inscription."}, status=400)

                clean_email = (preinscription.email or "").strip().lower()
                etudiant = Etudiant.objects.filter(email__iexact=clean_email).first()
                if not etudiant:
                    etudiant = Etudiant.objects.create(
                        nom=f"{preinscription.nom_candidat} {preinscription.prenom_candidat}".strip(),
                        contact=preinscription.telephone,
                        email=clean_email,
                        filiere=preinscription.filiere_souhaitee,
                        nom_parent=preinscription.nom_parent or "",
                        whatsapp_parent=preinscription.whatsapp_parent or "",
                        statut="Inscrit",
                    )
                else:
                    etudiant.filiere = preinscription.filiere_souhaitee
                    etudiant.nom_parent = preinscription.nom_parent or etudiant.nom_parent
                    etudiant.whatsapp_parent = preinscription.whatsapp_parent or etudiant.whatsapp_parent
                    etudiant.contact = preinscription.telephone or etudiant.contact
                    etudiant.statut = "Inscrit"
                    etudiant.save()

                year = None
                year_id = get_current_academic_year_id()
                if year_id:
                    try:
                        year = AnneeAcademique.objects.filter(id=year_id).first()
                    except Exception:
                        year = None
                if not year:
                    year = AnneeAcademique.objects.filter(est_active=True).first()

                annee_libelle = year.libelle if year else "(non défini)"

                # Trouver la classe correspondant à filière + niveau + année
                classe = None
                if year:
                    classe = Classe.objects.filter(
                        filiere=preinscription.filiere_souhaitee,
                        niveau=preinscription.niveau_souhaite,
                        annee_academique=year,
                    ).first()

                existing_inscription = Inscription.objects.filter(
                    etudiant=etudiant,
                    niveau=preinscription.niveau_souhaite,
                    annee_academique_ref=year if year else None,
                ).first()

                if not existing_inscription:
                    inscription = Inscription.objects.create(
                        etudiant=etudiant,
                        classe=classe,
                        niveau=preinscription.niveau_souhaite,
                        annee_academique=annee_libelle,
                        annee_academique_ref=year if year else None,
                    )
                elif not existing_inscription.classe and classe:
                    existing_inscription.classe = classe
                    existing_inscription.save()

                # Enregistrer les paiements initiaux si des montants ont été versés
                montant_inscription = Decimal(str(request.data.get("montant_inscription_verse", "0") or "0"))
                montant_formation = Decimal(str(request.data.get("montant_formation_verse", "0") or "0"))

                if classe and (montant_inscription > 0 or montant_formation > 0):
                    frais_inscription = Frais.objects.filter(
                        classe=classe, libelle__icontains="inscription"
                    ).first()
                    frais_formation = Frais.objects.filter(
                        classe=classe
                    ).exclude(libelle__icontains="inscription").first()

                    if montant_inscription > 0:
                        Paiement.objects.create(
                            etudiant=etudiant,
                            filiere=preinscription.filiere_souhaitee,
                            frais=frais_inscription,
                            paiement_type="INSCRIPTION",
                            montant_paye=montant_inscription,
                            moyen_paiement="cash",
                        )

                    if montant_formation > 0:
                        Paiement.objects.create(
                            etudiant=etudiant,
                            filiere=preinscription.filiere_souhaitee,
                            frais=frais_formation,
                            paiement_type="FORMATION",
                            montant_paye=montant_formation,
                            moyen_paiement="cash",
                        )

                preinscription.delete()

                return Response({
                    "message": "Pré-inscription approuvée et synchronisée.",
                    "etudiant_id": etudiant.id,
                })
        except Exception:
            traceback.print_exc()
            return Response({"error": "Impossible d'approuver"}, status=500)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        preinscription = self.get_object()
        if preinscription.statut != "EN_ATTENTE":
            return Response({"error": "Seules les pré-inscriptions en attente peuvent être rejetées."}, status=400)
        preinscription.delete()
        return Response({"message": "Pré-inscription rejetée."})

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

class EpreuveViewSet(OptimizedModelViewSet):
    queryset = Epreuve.objects.select_related(
        "filiere", "niveau", "module", "annee_academique", "semestre"
    ).all()
    serializer_class = EpreuveSerializer
    filterset_fields = ("filiere", "niveau", "module", "annee_academique", "semestre", "type_epreuve", "est_partage")
    search_fields = ("nom", "auteur", "module__nom", "filiere__nom")
    ordering = ("-annee_academique__libelle", "filiere__nom", "module__nom", "nom")

    def get_parsers(self):
        """Support multipart (file upload) + JSON."""
        from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
        return [MultiPartParser(), FormParser(), JSONParser()]

    def get_queryset(self):
        queryset = super().get_queryset()
        # Portail étudiant: si le paramètre student_view est présent, filtrer uniquement les épreuves partagées
        if self.request.query_params.get('student_view') == 'true':
            queryset = queryset.filter(est_partage=True)
        return queryset

    @action(detail=True, methods=['get'], url_path='download-sujet')
    def download_sujet(self, request, pk=None):
        epreuve = self.get_object()
        if not epreuve.fichier:
            return Response({"detail": "Sujet non trouvé."}, status=404)
        # Try to serve from local storage
        try:
            file_path = epreuve.fichier.path
            filename = get_valid_filename(os.path.basename(epreuve.fichier.name))
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
        except Exception:
            # Fallback: redirect to storage URL if available
            try:
                return HttpResponse(status=302, headers={'Location': epreuve.fichier.url})
            except Exception:
                return Response({"detail": "Impossible de récupérer le fichier."}, status=500)

    @action(detail=True, methods=['get'], url_path='download-corrige')
    def download_corrige(self, request, pk=None):
        epreuve = self.get_object()
        if not epreuve.corrige:
            return Response({"detail": "Corrigé non trouvé."}, status=404)
        try:
            file_path = epreuve.corrige.path
            filename = get_valid_filename(os.path.basename(epreuve.corrige.name))
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)
        except Exception:
            try:
                return HttpResponse(status=302, headers={'Location': epreuve.corrige.url})
            except Exception:
                return Response({"detail": "Impossible de récupérer le fichier."}, status=500)

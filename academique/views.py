import io
import traceback

import openpyxl
from django.db import transaction
from django.db.models import Q
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
from formations.models import Formation, Niveau
from modules.models import Module
from notes.models import Note
from paiements.models import Frais, Paiement

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
    DomaineSerializer,
    EvaluationSerializer,
    FaculteSerializer,
    FiliereSerializer,
    FraisSerializer,
    LevelSerializer,
    PreInscriptionSerializer,
    SemestreSerializer,
    SpecialiteSerializer,
)


class OptimizedModelViewSet(viewsets.ModelViewSet):
    search_fields = ()
    ordering_fields = "__all__"


class FaculteViewSet(OptimizedModelViewSet):
    queryset = Faculte.objects.prefetch_related("domaines").all()
    serializer_class = FaculteSerializer
    search_fields = ("nom", "code", "description")
    ordering = ("nom",)

    @action(detail=True, methods=["get"], url_path="domaines")
    def domaines(self, request, pk=None):
        serializer = DomaineSerializer(self.get_object().domaines.all(), many=True)
        return Response(serializer.data)


class DomaineViewSet(OptimizedModelViewSet):
    queryset = Domaine.objects.select_related("faculte").prefetch_related("filieres").all()
    serializer_class = DomaineSerializer
    filterset_fields = ("faculte",)
    search_fields = ("nom", "code", "description", "faculte__nom")
    ordering = ("faculte__nom", "nom")

    @action(detail=True, methods=["get"], url_path="filieres")
    def filieres(self, request, pk=None):
        serializer = FiliereSerializer(self.get_object().filieres.select_related("formation").all(), many=True)
        return Response(serializer.data)


class FiliereViewSet(OptimizedModelViewSet):
    queryset = Filiere.objects.select_related("domaine", "domaine__faculte", "formation").prefetch_related("specialites")
    serializer_class = FiliereSerializer
    filterset_fields = ("domaine", "domaine__faculte", "formation")
    search_fields = ("nom", "code", "description", "domaine__nom", "formation__intitule")
    ordering = ("domaine__nom", "nom")

    @action(detail=True, methods=["get"], url_path="specialites")
    def specialites(self, request, pk=None):
        serializer = SpecialiteSerializer(self.get_object().specialites.all(), many=True)
        return Response(serializer.data)


class SpecialiteViewSet(OptimizedModelViewSet):
    queryset = Specialite.objects.select_related("filiere", "filiere__domaine").prefetch_related("cycles").all()
    serializer_class = SpecialiteSerializer
    filterset_fields = ("filiere", "filiere__domaine")
    search_fields = ("nom", "code", "description", "filiere__nom")
    ordering = ("filiere__nom", "nom")

    @action(detail=True, methods=["get"], url_path="cycles")
    def cycles(self, request, pk=None):
        serializer = CycleSerializer(self.get_object().cycles.all(), many=True)
        return Response(serializer.data)


class CycleViewSet(OptimizedModelViewSet):
    queryset = Cycle.objects.select_related("specialite", "specialite__filiere").prefetch_related("niveaux").all()
    serializer_class = CycleSerializer
    filterset_fields = ("specialite", "specialite__filiere")
    search_fields = ("nom", "code", "description", "specialite__nom")
    ordering = ("specialite__nom", "ordre", "nom")

    @action(detail=True, methods=["get"], url_path="levels")
    def levels(self, request, pk=None):
        serializer = LevelSerializer(self.get_object().niveaux.prefetch_related("modules").all(), many=True)
        return Response(serializer.data)


class LevelViewSet(OptimizedModelViewSet):
    queryset = Niveau.objects.select_related("formation", "cycle", "cycle__specialite").prefetch_related("modules").all()
    serializer_class = LevelSerializer
    filterset_fields = ("formation", "cycle", "cycle__specialite")
    search_fields = ("nom", "formation__intitule", "cycle__nom", "cycle__specialite__nom")
    ordering = ("formation__intitule", "nom")

    @action(detail=True, methods=["get"], url_path="courses")
    def courses(self, request, pk=None):
        niveau = self.get_object()
        modules = niveau.modules.all()
        if not modules.exists():
            modules = niveau.formation.modules.all()
        serializer = CourseSerializer(modules, many=True)
        return Response(serializer.data)


class CourseViewSet(OptimizedModelViewSet):
    queryset = Module.objects.prefetch_related("niveaux", "formations").all()
    serializer_class = CourseSerializer
    filterset_fields = ("has_tp",)
    search_fields = ("nom",)
    ordering = ("nom",)


class AnneeAcademiqueViewSet(OptimizedModelViewSet):
    queryset = AnneeAcademique.objects.prefetch_related("semestres", "classes").all()
    serializer_class = AnneeAcademiqueSerializer
    filterset_fields = ("est_active",)
    search_fields = ("libelle", "description")
    ordering = ("-libelle",)


class ClasseViewSet(OptimizedModelViewSet):
    queryset = (
        Classe.objects.select_related(
            "specialite",
            "specialite__filiere",
            "cycle",
            "niveau",
            "niveau__formation",
            "annee_academique",
        )
        .prefetch_related("modules")
        .all()
    )
    serializer_class = ClasseSerializer
    filterset_fields = ("specialite", "cycle", "niveau", "annee_academique")
    search_fields = (
        "nom",
        "description",
        "specialite__nom",
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
    filterset_fields = ("module", "classe", "evaluation", "session")
    search_fields = ("etudiant__nom", "module__nom", "classe__nom", "session")
    ordering = ("etudiant__nom",)

    @action(detail=False, methods=["get"], url_path="par-module")
    def par_module(self, request):
        module_id = request.query_params.get("module_id")
        session = request.query_params.get("session")

        if not module_id or not session:
            return Response({"detail": "module_id et session sont requis."}, status=status.HTTP_400_BAD_REQUEST)

        notes = (
            Note.objects.filter(module_id=module_id, session=session)
            .select_related("etudiant", "module")
            .order_by("etudiant__nom")
        )

        data = [
            {
                "id": note.id,
                "etudiant_id": note.etudiant_id,
                "etudiant_nom": note.etudiant.nom,
                "etudiant_matricule": note.etudiant.matricule,
                "module_id": note.module_id,
                "module_nom": note.module.nom,
                "session": note.session,
                "note_cc": note.note_cc,
                "note_sn": note.note_sn,
                "note_tp": note.note_tp,
                "note_rattrapage": note.note_rattrapage,
                "note_finale": note.note_finale,
                "note_sur_20": float(note.note_finale) if note.note_finale is not None else None,
                "module_has_tp": bool(getattr(note.module, "has_tp", False)),
            }
            for note in notes
        ]
        return Response(data)

    @action(detail=False, methods=["get"], url_path="par-filiere-niveau")
    def par_filiere_niveau(self, request):
        filiere_id = request.query_params.get("filiere_id")
        session = request.query_params.get("session")

        if not filiere_id or not session:
            return Response(
                {"detail": "filiere_id et session sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            formation = Formation.objects.get(pk=filiere_id)
        except Formation.DoesNotExist:
            return Response({"detail": "Filière introuvable."}, status=status.HTTP_404_NOT_FOUND)

        niveaux = list(Niveau.objects.filter(formation=formation).order_by("id"))
        data = {
            "filiere_id": formation.id,
            "filiere_nom": formation.intitule,
            "session": session,
            "niveaux": [],
        }

        for niveau in niveaux:
            modules = list(niveau.modules.all()) or list(formation.modules.all())
            inscriptions = Inscription.objects.filter(niveau=niveau).select_related("etudiant")
            etudiants_data = []

            for inscription in inscriptions:
                etudiant = inscription.etudiant
                notes = []
                total_coeff = 0
                total_points = 0.0

                for module in modules:
                    note = (
                        Note.objects.filter(etudiant=etudiant, module=module, session=session)
                        .select_related("module")
                        .first()
                    )
                    note_sur_20 = float(note.note_finale) if note and note.note_finale is not None else None
                    coeff = getattr(module, "coefficient", 1) or 1

                    if note_sur_20 is not None:
                        total_coeff += coeff
                        total_points += note_sur_20 * coeff

                    notes.append(
                        {
                            "module_id": module.id,
                            "module_nom": module.nom,
                            "module_has_tp": bool(getattr(module, "has_tp", False)),
                            "note_cc": note.note_cc if note else None,
                            "note_sn": note.note_sn if note else None,
                            "note_tp": note.note_tp if note else None,
                            "note_rattrapage": note.note_rattrapage if note else None,
                            "note_finale": note.note_finale if note else None,
                            "note_sur_20": note_sur_20,
                        }
                    )

                moyenne_niveau = round(total_points / total_coeff, 2) if total_coeff > 0 else None
                etudiants_data.append(
                    {
                        "etudiant_id": etudiant.id,
                        "etudiant_nom": etudiant.nom,
                        "etudiant_matricule": etudiant.matricule,
                        "moyenne_niveau": moyenne_niveau,
                        "notes": notes,
                    }
                )

            etudiants_data.sort(key=lambda item: (item["moyenne_niveau"] is None, -(item["moyenne_niveau"] or 0)))
            for index, item in enumerate(etudiants_data, start=1):
                item["rang"] = index

            data["niveaux"].append(
                {
                    "niveau_id": niveau.id,
                    "niveau_nom": niveau.nom,
                    "modules": [
                        {"id": module.id, "nom": module.nom, "has_tp": bool(getattr(module, "has_tp", False))}
                        for module in modules
                    ],
                    "etudiants": etudiants_data,
                }
            )

        return Response(data)

    @action(detail=True, methods=["get"], url_path="details")
    def details(self, request, pk=None):
        session = request.query_params.get("session")
        if not session:
            return Response({"detail": "session est requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"detail": "Étudiant introuvable."}, status=status.HTTP_404_NOT_FOUND)

        notes = Note.objects.filter(etudiant=etudiant, session=session).select_related("module")
        data = [
            {
                "id": note.id,
                "etudiant_id": etudiant.id,
                "session": note.session,
                "module_id": note.module.id,
                "module_nom": note.module.nom,
                "note_cc": note.note_cc,
                "note_sn": note.note_sn,
                "note_tp": note.note_tp,
                "note_rattrapage": note.note_rattrapage,
                "note_finale": note.note_finale,
                "note_sur_20": float(note.note_finale) if note.note_finale is not None else None,
                "module_has_tp": bool(getattr(note.module, "has_tp", False)),
            }
            for note in notes
        ]
        return Response(data)

    @action(detail=False, methods=["get"], url_path="export-template")
    def export_template(self, request):
        evaluation_id = request.query_params.get("evaluation")
        if not evaluation_id:
            return Response({"detail": "evaluation_id est requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evaluation = Evaluation.objects.get(pk=evaluation_id)
            inscriptions = (
                Inscription.objects.filter(
                    Q(classe=evaluation.classe)
                    | Q(
                        classe__isnull=True,
                        niveau=evaluation.classe.niveau,
                        annee_academique_ref=evaluation.classe.annee_academique,
                    )
                )
                .select_related("etudiant")
                .distinct()
                .order_by("etudiant__nom")
            )

            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.title = "Saisie des Notes"
            worksheet.append(["ID Étudiant", "Matricule", "Nom", "Note (Sur 20)"])

            for inscription in inscriptions:
                worksheet.append([inscription.etudiant.id, inscription.etudiant.matricule, inscription.etudiant.nom, ""])

            for cell in worksheet[1]:
                cell.font = Font(bold=True)

            output = io.BytesIO()
            workbook.save(output)
            output.seek(0)

            filename = get_valid_filename(f"Modele_Notes_{evaluation.classe.nom}_{evaluation.libelle}.xlsx")
            response = HttpResponse(
                output.read(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = content_disposition_header(True, filename)
            return response
        except Evaluation.DoesNotExist:
            return Response({"detail": "Évaluation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            print(traceback.format_exc())
            return Response({"detail": f"Erreur interne: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"], url_path="export-template-niveau")
    def export_template_niveau(self, request):
        filiere_id = request.query_params.get("filiere")
        niveau_id = request.query_params.get("niveau")
        session = request.query_params.get("session")

        if not filiere_id or not niveau_id or not session:
            return Response(
                {"detail": "filiere, niveau et session sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            formation = Formation.objects.get(pk=filiere_id)
            niveau = Niveau.objects.get(pk=niveau_id, formation=formation)
        except Formation.DoesNotExist:
            return Response({"detail": "Filière introuvable."}, status=status.HTTP_404_NOT_FOUND)
        except Niveau.DoesNotExist:
            return Response({"detail": "Niveau introuvable pour cette filière."}, status=status.HTTP_404_NOT_FOUND)

        modules = list(niveau.modules.all()) or list(formation.modules.all())

        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Saisie des Notes"

        tech_headers = ["etudiant_id", "matricule", "nom"]
        display_headers = ["ID Étudiant", "Matricule", "Nom"]

        for module in modules:
            tech_headers.extend([f"module_{module.id}_cc", f"module_{module.id}_sn"])
            display_headers.extend([f"{module.nom} - CC", f"{module.nom} - SN"])
            if bool(getattr(module, "has_tp", False)):
                tech_headers.append(f"module_{module.id}_tp")
                display_headers.append(f"{module.nom} - TP")

        worksheet.append(tech_headers)
        worksheet.append(display_headers)

        for cell in worksheet[2]:
            cell.font = Font(bold=True)

        for inscription in Inscription.objects.filter(niveau=niveau).select_related("etudiant").order_by("etudiant__nom"):
            worksheet.append(
                [inscription.etudiant.id, inscription.etudiant.matricule, inscription.etudiant.nom]
                + ([""] * (len(tech_headers) - 3))
            )

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        filename = get_valid_filename(f"Modele_Notes_{formation.intitule}_{niveau.nom}_{session}.xlsx")
        response = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = content_disposition_header(True, filename)
        return response

    @action(detail=False, methods=["post"], url_path="import-notes")
    def import_notes(self, request):
        evaluation_id = request.data.get("evaluation")
        excel_file = request.FILES.get("file")

        if not evaluation_id or not excel_file:
            return Response({"detail": "evaluation et file sont requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evaluation = Evaluation.objects.get(pk=evaluation_id)
            workbook = openpyxl.load_workbook(excel_file)
            worksheet = workbook.active

            success_count = 0
            errors = []

            for row in worksheet.iter_rows(min_row=2, values_only=True):
                values = list(row)
                if len(values) >= 5:
                    etudiant_id, _matricule, _nom, _prenom, note_value = values[:5]
                else:
                    etudiant_id, _matricule, _nom, note_value = (values + [None] * 4)[:4]

                if etudiant_id in (None, "") or note_value in (None, ""):
                    continue

                try:
                    Note.objects.update_or_create(
                        etudiant_id=etudiant_id,
                        evaluation=evaluation,
                        defaults={
                            "module": evaluation.module,
                            "classe": evaluation.classe,
                            "note_cc": float(note_value),
                            "session": evaluation.semestre.nom if evaluation.semestre else "Semestre 1",
                            "annee_academique": evaluation.classe.annee_academique.libelle,
                        },
                    )
                    success_count += 1
                except Exception as exc:
                    errors.append(f"Erreur étudiant ID {etudiant_id}: {exc}")

            return Response({"message": f"{success_count} notes importées avec succès.", "errors": errors})
        except Evaluation.DoesNotExist:
            return Response({"detail": "Évaluation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            print(traceback.format_exc())
            return Response(
                {"detail": f"Erreur lors de la lecture du fichier: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="import-notes-niveau")
    def import_notes_niveau(self, request):
        filiere_id = request.data.get("filiere")
        niveau_id = request.data.get("niveau")
        session = request.data.get("session")
        excel_file = request.FILES.get("file")

        if not filiere_id or not niveau_id or not session or not excel_file:
            return Response(
                {"detail": "filiere, niveau, session et file sont requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            formation = Formation.objects.get(pk=filiere_id)
            niveau = Niveau.objects.get(pk=niveau_id, formation=formation)
        except Formation.DoesNotExist:
            return Response({"detail": "Filière introuvable."}, status=status.HTTP_404_NOT_FOUND)
        except Niveau.DoesNotExist:
            return Response({"detail": "Niveau introuvable pour cette filière."}, status=status.HTTP_404_NOT_FOUND)

        try:
            workbook = openpyxl.load_workbook(excel_file)
            worksheet = workbook.active
            tech_headers = [cell.value for cell in worksheet[1]]

            if not tech_headers or tech_headers[:3] != ["etudiant_id", "matricule", "nom"]:
                return Response(
                    {"detail": "Template invalide: en-têtes techniques manquants."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            col_map = {}
            for index, key in enumerate(tech_headers, start=1):
                if isinstance(key, str) and key.startswith("module_") and any(suffix in key for suffix in ("_cc", "_sn", "_tp")):
                    parts = key.split("_")
                    if len(parts) == 3 and parts[1].isdigit():
                        col_map[index] = (int(parts[1]), parts[2])

            success = 0
            errors = []

            for row in worksheet.iter_rows(min_row=3, values_only=False):
                etudiant_id = row[0].value
                if etudiant_id in (None, ""):
                    continue

                for col_idx, (module_id, field) in col_map.items():
                    value = row[col_idx - 1].value
                    if value in (None, ""):
                        continue
                    try:
                        note_obj, _ = Note.objects.update_or_create(
                            etudiant_id=int(etudiant_id),
                            module_id=module_id,
                            session=session,
                            defaults={
                                "classe": None,
                                "evaluation": None,
                                "annee_academique": getattr(
                                    AnneeAcademique.objects.filter(est_active=True).order_by("-libelle").first(),
                                    "libelle",
                                    "2024-2025",
                                ),
                                field: float(value),
                            },
                        )
                        note_obj.save()
                        success += 1
                    except Exception as exc:
                        errors.append(f"Étudiant {etudiant_id}, module {module_id} ({field}): {exc}")

            return Response({"message": f"Import terminé. {success} valeurs importées.", "errors": errors})
        except Exception as exc:
            print(traceback.format_exc())
            return Response(
                {"detail": f"Erreur lors de la lecture du fichier: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FraisViewSet(OptimizedModelViewSet):
    queryset = Frais.objects.select_related("classe").all()
    serializer_class = FraisSerializer


class AcademicPaiementViewSet(OptimizedModelViewSet):
    queryset = Paiement.objects.select_related("etudiant", "formation", "frais", "frais__classe").all()
    serializer_class = AcademicPaiementSerializer


class AcademicEmploiDuTempsViewSet(OptimizedModelViewSet):
    queryset = EmploiDuTemps.objects.select_related("classe", "formation", "niveau", "module", "formateur").all()
    serializer_class = AcademicEmploiDuTempsSerializer


class PreInscriptionViewSet(OptimizedModelViewSet):
    queryset = PreInscription.objects.select_related("filiere_souhaitee", "formation_souhaitee", "niveau_souhaite").all()
    serializer_class = PreInscriptionSerializer
    filterset_fields = ("statut", "filiere_souhaitee", "formation_souhaitee", "niveau_souhaite")
    search_fields = ("nom_candidat", "prenom_candidat", "email", "telephone")
    ordering = ("-created_at",)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        preinscription = self.get_object()
        serializer = self.get_serializer(preinscription, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        montant_inscription = serializer.validated_data.get("montant_inscription_verse")
        montant_formation = serializer.validated_data.get("montant_formation_verse")

        with transaction.atomic():
            preinscription.statut = "APPROUVEE"
            preinscription.save(update_fields=["statut", "updated_at"])
            self._create_etudiant_and_inscription(preinscription, montant_inscription, montant_formation)

        etudiant = Etudiant.objects.filter(email=preinscription.email).first()
        has_inscription = Inscription.objects.filter(etudiant__email=preinscription.email).exists()
        return Response(
            {
                "message": "Pré-inscription approuvée et synchronisée.",
                "preinscription_id": preinscription.id,
                "etudiant_id": etudiant.id if etudiant else None,
                "inscription_created": bool(has_inscription),
            }
        )

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        preinscription = self.get_object()
        preinscription.statut = "REJETEE"
        preinscription.save(update_fields=["statut", "updated_at"])
        return Response(
            {
                "message": "Pré-inscription désapprouvée.",
                "preinscription_id": preinscription.id,
            }
        )

    def perform_update(self, serializer):
        montant_inscription = serializer.validated_data.get("montant_inscription_verse")
        montant_formation = serializer.validated_data.get("montant_formation_verse")
        previous_status = getattr(serializer.instance, "statut", None)
        with transaction.atomic():
            instance = serializer.save()
            if previous_status != "APPROUVEE" and instance.statut == "APPROUVEE":
                self._create_etudiant_and_inscription(instance, montant_inscription, montant_formation)

    def _create_payment_records(self, etudiant, montant_inscription=None, montant_formation=None):
        if not etudiant or not etudiant.filiere:
            return

        if montant_inscription in ("", None) or montant_inscription == 0:
            montant_inscription = None
        if montant_formation in ("", None) or montant_formation == 0:
            montant_formation = None

        formation = etudiant.filiere
        if montant_inscription is not None:
            Paiement.objects.create(
                etudiant=etudiant,
                formation=formation,
                paiement_type="INSCRIPTION",
                montant_paye=montant_inscription,
            )
        if montant_formation is not None:
            Paiement.objects.create(
                etudiant=etudiant,
                formation=formation,
                paiement_type="FORMATION",
                montant_paye=montant_formation,
            )

    def _create_etudiant_and_inscription(self, preinscription, montant_inscription=None, montant_formation=None):
        formation = preinscription.formation_souhaitee or getattr(preinscription.filiere_souhaitee, "formation", None)
        if not formation:
            raise ValidationError(
                {
                    "formation_souhaitee": "Impossible d'inscrire: la formation choisie n'est pas liée à une filière valide.",
                    "filiere_souhaitee": "Impossible d'inscrire: la formation choisie n'est pas liée à une filière valide.",
                }
            )

        annee = AnneeAcademique.objects.filter(est_active=True).order_by("-libelle").first()
        annee_libelle = annee.libelle if annee else str(timezone.now().year)

        etudiant, created = Etudiant.objects.get_or_create(
            email=preinscription.email,
            defaults={
                "nom": f"{preinscription.nom_candidat} {preinscription.prenom_candidat}".strip(),
                "contact": preinscription.telephone,
                "filiere": formation,
                "statut": "Inscrit",
            },
        )

        if not created:
            changed = False
            full_name = f"{preinscription.nom_candidat} {preinscription.prenom_candidat}".strip()

            if full_name and etudiant.nom != full_name:
                etudiant.nom = full_name
                changed = True
            if preinscription.telephone and etudiant.contact != preinscription.telephone:
                etudiant.contact = preinscription.telephone
                changed = True
            if etudiant.filiere_id != formation.id:
                etudiant.filiere = formation
                changed = True
            if etudiant.statut != "Inscrit":
                etudiant.statut = "Inscrit"
                changed = True

            if changed:
                etudiant.save()

        if preinscription.niveau_souhaite_id:
            Inscription.objects.get_or_create(
                etudiant=etudiant,
                niveau=preinscription.niveau_souhaite,
                annee_academique=annee_libelle,
                defaults={"annee_academique_ref": annee, "classe": None},
            )

        self._create_payment_records(etudiant, montant_inscription, montant_formation)

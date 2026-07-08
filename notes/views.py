from django.db.models import Avg, Q
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Note, Etudiant, Module
from etudiants.models import Inscription
from academique.models import Filiere, Niveau, CourseAssignment, Evaluation, Classe, AnneeAcademique
from .serializers import NoteSerializer, NoteSummarySerializer, NoteFiliereSerializer
from academique.middleware import get_current_academic_year_id


class NoteViewSet(viewsets.ModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'etudiant', 'etudiant__filiere', 'module', 'classe', 'evaluation'
        )

        # Filtre global par année académique
        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(
                Q(annee_academique_ref_id=year_id) |
                Q(annee_academique_ref__isnull=True, classe__annee_academique_id=year_id) |
                Q(annee_academique_ref__isnull=True, classe__isnull=True, annee_academique=AnneeAcademique.objects.filter(pk=year_id).values_list('libelle', flat=True)[:1])
            )

        classe_id = self.request.query_params.get("classe")
        evaluation_id = self.request.query_params.get("evaluation")

        # Filtre automatique si c'est un étudiant qui demande ses propres notes
        if self.request.user.is_authenticated and getattr(self.request.user, 'role', '') == 'etudiant':
            etudiant = getattr(self.request.user, 'etudiant_profile', None)
            if etudiant:
                queryset = queryset.filter(etudiant=etudiant)

        if classe_id:
            queryset = queryset.filter(classe_id=classe_id)
        if evaluation_id:
            queryset = queryset.filter(evaluation_id=evaluation_id)
        return queryset

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Récupère les notes de l'étudiant connecté."""
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil étudiant introuvable"}, status=404)

        session = request.query_params.get("session")
        notes = Note.objects.filter(etudiant=etudiant)
        
        year_id = get_current_academic_year_id()
        if year_id:
            notes = notes.filter(classe__annee_academique_id=year_id)

        if session:
            notes = notes.filter(session=session)
        
        notes = notes.select_related("module")
        
        data = []
        for note in notes:
            data.append({
                "id": note.id,
                "module_nom": note.module.nom,
                "session": note.session,
                "note_cc": note.note_cc,
                "note_sn": note.note_sn,
                "note_rattrapage": note.note_rattrapage,
                "note_finale": note.note_finale,
                "coefficient": getattr(note.module, 'coefficient', 1),
                "credits": getattr(note.module, 'credits', 0),
            })
        return Response(data)

    def get_serializer_class(self):
        if self.action == "list" and self.request.query_params.get("summary") == "true":
            return NoteSummarySerializer
        return NoteSerializer

    def list(self, request, *args, **kwargs):
        if request.query_params.get("summary") == "true":
            notes = (
                Note.objects
            )
            
            year_id = get_current_academic_year_id()
            if year_id:
                notes = notes.filter(classe__annee_academique_id=year_id)

            notes = (
                notes.values(
                    "etudiant_id",
                    "etudiant__nom",
                    "etudiant__matricule",
                    "etudiant__filiere__nom",
                    "session"
                )
                .distinct()
            )

            data = []
            for n in notes:
                etudiant_id = n["etudiant_id"]
                session = n["session"]
                moyenne_sur_20 = Note.moyenne_etudiant(Etudiant.objects.get(pk=etudiant_id), session=session)
                if moyenne_sur_20 is None:
                    moyenne_sur_20 = 0

                if moyenne_sur_20 < 10:
                    mention = "Échec"
                elif 10 <= moyenne_sur_20 < 12:
                    mention = "Passable"
                elif 12 <= moyenne_sur_20 < 14:
                    mention = "Assez Bien"
                elif 14 <= moyenne_sur_20 < 16:
                    mention = "Bien"
                else:
                    mention = "Très Bien"

                data.append({
                    "etudiant_id": etudiant_id,
                    "etudiant_nom": n["etudiant__nom"],
                    "etudiant_matricule": n["etudiant__matricule"],
                    "formation": n["etudiant__filiere__nom"],
                    "session": session,
                    "moyenne_generale": moyenne_sur_20,
                    "mention": mention,
                })

            serializer = self.get_serializer(data, many=True)
            return Response(serializer.data)

        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="par-module")
    def par_module(self, request):
        module_id = request.query_params.get("module_id")
        session = request.query_params.get("session")

        if not module_id:
            return Response({"error": "module_id requis"}, status=400)

        try:
            module = Module.objects.get(pk=module_id)
        except Module.DoesNotExist:
            return Response({"error": "Module introuvable"}, status=404)

        etudiants = Etudiant.objects.filter(notes__module=module, notes__session=session).distinct()

        data = []
        for etudiant in etudiants:
            note = Note.objects.filter(
                etudiant=etudiant,
                module=module,
                session=session
            ).first()

            note_sur_20 = None
            if note and note.note_finale is not None:
                note_sur_20 = float(note.note_finale)

            data.append({
                "id": note.id if note else None,
                "etudiant_id": etudiant.id,
                "etudiant_nom": etudiant.nom,
                "etudiant_matricule": etudiant.matricule,
                "module_id": module.id,
                "module_nom": module.nom,
                "session": session,
                "note_cc": note.note_cc if note else None,
                "note_sn": note.note_sn if note else None,
                "note_rattrapage": note.note_rattrapage if note else None,
                "note_finale": note.note_finale if note else None,
                "note_sur_20": note_sur_20,
                "besoin_rattrapage": (note.besoin_rattrapage if note else None),
            })

        return Response(data)

    @action(detail=False, methods=["get"], url_path="par-filiere")
    def par_filiere(self, request):
        filiere_id = request.query_params.get("filiere_id")
        session = request.query_params.get("session")

        if not filiere_id:
            return Response({"error": "filiere_id requis"}, status=400)

        try:
            filiere = Filiere.objects.get(pk=filiere_id)
        except Filiere.DoesNotExist:
            return Response({"error": "Filière introuvable"}, status=404)

        # In the new system, modules are related to Filiere via CourseAssignment
        module_ids = CourseAssignment.objects.filter(filiere=filiere).values_list('module_id', flat=True)
        modules = Module.objects.filter(id__in=module_ids)
        etudiants = Etudiant.objects.filter(filiere_id=filiere_id).distinct()

        data = {
            "filiere_id": filiere.id,
            "filiere_nom": filiere.nom,
            "modules": [{"id": m.id, "nom": m.nom} for m in modules],
            "etudiants": []
        }

        for etudiant in etudiants:
            etudiant_data = {
                "etudiant_id": etudiant.id,
                "etudiant_nom": etudiant.nom,
                "etudiant_matricule": etudiant.matricule,
                "session": session,
                "notes": []
            }
            for module in modules:
                note = Note.objects.filter(
                    etudiant=etudiant,
                    module=module,
                    session=session
                ).first()
                etudiant_data["notes"].append({
                    "module_id": module.id,
                    "module_nom": module.nom,
                    "note_cc": note.note_cc if note else None,
                    "note_sn": note.note_sn if note else None,
                    "note_rattrapage": note.note_rattrapage if note else None,
                    "note_finale": note.note_finale if note else None,
                    "note_sur_20": float(note.note_finale) if note and note.note_finale else None
                })
            data["etudiants"].append(etudiant_data)

        serializer = NoteFiliereSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="par-filiere-niveau")
    def par_filiere_niveau(self, request):
        filiere_id = request.query_params.get("filiere_id")
        session = request.query_params.get("session")

        if not filiere_id:
            return Response({"error": "filiere_id requis"}, status=400)

        try:
            # We filter by filiere
            filiere = Filiere.objects.get(pk=filiere_id)
        except Filiere.DoesNotExist:
            return Response({"error": "Filière introuvable"}, status=404)

        # In the new system, we get levels from the filiere structure (Cycle -> Niveau)
        niveaux = Niveau.objects.filter(cycle__filiere=filiere)

        data = {
            "filiere_id": filiere.id,
            "filiere_nom": filiere.nom,
            "session": session,
            "niveaux": []
        }

        for niveau in niveaux:
            # Modules assigned to this (filiere, level)
            module_ids = CourseAssignment.objects.filter(filiere=filiere, niveau=niveau).values_list('module_id', flat=True)
            modules = Module.objects.filter(id__in=module_ids)
            etudiants = Etudiant.objects.filter(inscriptions__niveau=niveau).distinct()
            etudiants_data = []

            for etudiant in etudiants:
                notes = []
                total_points = 0.0
                total_coeff = 0.0

                for module in modules:
                    note = Note.objects.filter(
                        etudiant=etudiant,
                        module=module,
                        session=session
                    ).first()

                    note_finale = note.note_finale if note else None
                    coeff = getattr(module, "coefficient", 1) or 1
                    if note_finale is not None:
                        total_points += float(note_finale) * coeff
                        total_coeff += coeff

                    notes.append({
                        "module_id": module.id,
                        "module_nom": module.nom,
                        "note_cc": note.note_cc if note else None,
                        "note_sn": note.note_sn if note else None,
                        "note_rattrapage": note.note_rattrapage if note else None,
                        "note_finale": note_finale,
                        "note_sur_20": float(note_finale) if note_finale is not None else None
                    })

                moyenne_niveau = round(total_points / total_coeff, 2) if total_coeff > 0 else None
                etudiants_data.append({
                    "etudiant_id": etudiant.id,
                    "etudiant_nom": etudiant.nom,
                    "etudiant_matricule": etudiant.matricule,
                    "moyenne_niveau": moyenne_niveau,
                    "notes": notes
                })

            etudiants_data.sort(key=lambda x: (x["moyenne_niveau"] is None, -(x["moyenne_niveau"] or 0)))
            for idx, e in enumerate(etudiants_data, start=1):
                e["rang"] = idx

            data["niveaux"].append({
                "niveau_id": niveau.id,
                "niveau_nom": niveau.nom,
                "modules": [{"id": m.id, "nom": m.nom} for m in modules],
                "etudiants": etudiants_data
            })

        return Response(data)

    @action(detail=False, methods=["get"], url_path="saisie-groupee")
    def saisie_groupee(self, request):
        evaluation_id = request.query_params.get("evaluation")
        classe_id = request.query_params.get("classe")
        module_id = request.query_params.get("module")

        if evaluation_id:
            try:
                evaluation = Evaluation.objects.get(pk=evaluation_id)
                classe = evaluation.classe
                module = evaluation.module
            except Evaluation.DoesNotExist:
                return Response({"error": "Évaluation introuvable"}, status=404)
        elif classe_id and module_id:
            try:
                classe = Classe.objects.get(pk=classe_id)
                module = Module.objects.get(pk=module_id)
                evaluation = None
            except (Classe.DoesNotExist, Module.DoesNotExist):
                return Response({"error": "Classe ou Module introuvable"}, status=404)
        else:
            return Response({"error": "Paramètres manquants (evaluation_id ou classe_id+module_id)"}, status=400)

        # Get all students enrolled in this class
        inscriptions = Inscription.objects.filter(classe=classe).select_related('etudiant')
        
        data = []
        for ins in inscriptions:
            etudiant = ins.etudiant
            # Fetch existing note if any
            note_query = Note.objects.filter(etudiant=etudiant, module=module)
            if evaluation:
                note_query = note_query.filter(evaluation=evaluation)
            else:
                note_query = note_query.filter(classe=classe)
            
            note = note_query.first()

            data.append({
                "etudiant_id": etudiant.id,
                "etudiant_nom": etudiant.nom,
                "etudiant_matricule": etudiant.matricule,
                "classe_id": classe.id,
                "module_id": module.id,
                "evaluation_id": evaluation.id if evaluation else None,
                "note_id": note.id if note else None,
                "note_cc": note.note_cc if note else None,
                "note_sn": note.note_sn if note else None,
                "note_rattrapage": note.note_rattrapage if note else None,
                "note_finale": note.note_finale if note else None,
            })

        return Response(data)

    @action(detail=False, methods=["post"], url_path="batch-save")
    def batch_save(self, request):
        notes_data = request.data.get("notes", [])
        if not notes_data:
            return Response({"error": "Aucune donnée fournie"}, status=400)

        results = []
        for item in notes_data:
            etudiant_id = item.get("etudiant_id")
            module_id = item.get("module_id")
            classe_id = item.get("classe_id")
            evaluation_id = item.get("evaluation_id")
            
            # Find existing note or create new one
            defaults = {
                "note_cc": item.get("note_cc"),
                "note_sn": item.get("note_sn"),
                "note_rattrapage": item.get("note_rattrapage"),
                "classe_id": classe_id,
                "evaluation_id": evaluation_id,
            }
            
            # Filter criteria
            filter_kwargs = {
                "etudiant_id": etudiant_id,
                "module_id": module_id,
            }
            if evaluation_id:
                filter_kwargs["evaluation_id"] = evaluation_id
            else:
                filter_kwargs["classe_id"] = classe_id
                filter_kwargs["evaluation__isnull"] = True

            note, created = Note.objects.update_or_create(
                **filter_kwargs,
                defaults=defaults
            )
            results.append(NoteSerializer(note).data)

        return Response({"message": f"{len(results)} notes enregistrées", "data": results}, status=200)

    @action(detail=True, methods=["get"], url_path="details")
    def details(self, request, pk=None):
        session = request.query_params.get("session")

        if not session:
            return Response({"error": "session requis"}, status=400)

        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Étudiant introuvable"}, status=404)

        notes = Note.objects.filter(etudiant=etudiant, session=session).select_related("module")

        data = []
        for note in notes:
            data.append({
                "id": note.id,
                "etudiant_id": etudiant.id,
                "session": note.session,
                "module_id": note.module.id,
                "module_nom": note.module.nom,
                "note_cc": note.note_cc,
                "note_sn": note.note_sn,
                "note_rattrapage": note.note_rattrapage,
                "note_finale": note.note_finale,
                "note_sur_20": float(note.note_finale) if note and note.note_finale else None,
            })

        return Response(data)

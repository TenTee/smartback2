from django.db.models import Avg
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Note, Etudiant, Module
from etudiants.models import Inscription
from formations.models import Formation
from .serializers import NoteSerializer, NoteSummarySerializer, NoteFiliereSerializer


class NoteViewSet(viewsets.ModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        classe_id = self.request.query_params.get("classe")
        evaluation_id = self.request.query_params.get("evaluation")
        if classe_id:
            queryset = queryset.filter(classe_id=classe_id)
        if evaluation_id:
            queryset = queryset.filter(evaluation_id=evaluation_id)
        return queryset

    def get_serializer_class(self):
        if self.action == "list" and self.request.query_params.get("summary") == "true":
            return NoteSummarySerializer
        return NoteSerializer

    def list(self, request, *args, **kwargs):
        if request.query_params.get("summary") == "true":
            notes = (
                Note.objects.values(
                    "etudiant_id",
                    "etudiant__nom",
                    "etudiant__matricule",
                    "etudiant__filiere__intitule",
                    "session"
                )
                .distinct()
            )

            data = []
            for n in notes:
                etudiant_id = n["etudiant_id"]
                session = n["session"]
                moyenne_sur_20 = Note.moyenne_etudiant(etudiant_id, session=session)
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
                    "formation": n["etudiant__filiere__intitule"],
                    "session": session,
                    "moyenne_generale": moyenne_sur_20,
                    "mention": mention,
                })

            serializer = self.get_serializer(data, many=True)
            return Response(serializer.data)

        return super().list(request, *args, **kwargs)

    # ✅ Action pour filtrer par module
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
                "note_tp": note.note_tp if note else None,
                "note_rattrapage": note.note_rattrapage if note else None,
                "note_finale": note.note_finale if note else None,
                "note_sur_20": note_sur_20,
                "besoin_rattrapage": (note.besoin_rattrapage if note else None),
            })

        return Response(data)

    # ✅ Action pour filtrer par filière
    @action(detail=False, methods=["get"], url_path="par-filiere")
    def par_filiere(self, request):
        filiere_id = request.query_params.get("filiere_id")
        session = request.query_params.get("session")

        if not filiere_id:
            return Response({"error": "filiere_id requis"}, status=400)

        try:
            formation = Formation.objects.get(pk=filiere_id)
        except Formation.DoesNotExist:
            return Response({"error": "Filière introuvable"}, status=404)

        modules = formation.modules.all()
        etudiants = Etudiant.objects.filter(filiere_id=filiere_id).distinct()

        data = {
            "filiere_id": formation.id,
            "filiere_nom": formation.intitule,
            "modules": [{"id": m.id, "nom": m.nom, "has_tp": bool(getattr(m, "has_tp", False))} for m in modules],
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
                    "note_tp": note.note_tp if note else None,
                    "note_rattrapage": note.note_rattrapage if note else None,
                    "note_finale": note.note_finale if note else None,
                    "note_sur_20": float(note.note_finale) if note and note.note_finale else None
                })
            data["etudiants"].append(etudiant_data)

        serializer = NoteFiliereSerializer(data)
        return Response(serializer.data)

    # ✅ Notes par filière et par niveau avec classement
    @action(detail=False, methods=["get"], url_path="par-filiere-niveau")
    def par_filiere_niveau(self, request):
        filiere_id = request.query_params.get("filiere_id")
        session = request.query_params.get("session")

        if not filiere_id:
            return Response({"error": "filiere_id requis"}, status=400)

        try:
            formation = Formation.objects.get(pk=filiere_id)
        except Formation.DoesNotExist:
            return Response({"error": "Filière introuvable"}, status=404)

        niveaux = formation.niveaux.all()

        data = {
            "filiere_id": formation.id,
            "filiere_nom": formation.intitule,
            "session": session,
            "niveaux": []
        }

        for niveau in niveaux:
            modules = niveau.modules.all()
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
                        "note_tp": note.note_tp if note else None,
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

            # Classement par moyenne décroissante (None en dernier)
            etudiants_data.sort(key=lambda x: (x["moyenne_niveau"] is None, -(x["moyenne_niveau"] or 0)))
            for idx, e in enumerate(etudiants_data, start=1):
                e["rang"] = idx

            data["niveaux"].append({
                "niveau_id": niveau.id,
                "niveau_nom": niveau.nom,
                "modules": [{"id": m.id, "nom": m.nom, "has_tp": bool(getattr(m, "has_tp", False))} for m in modules],
                "etudiants": etudiants_data
            })

        return Response(data)

    # ✅ Action pour récupérer les notes d’un étudiant dans tous ses modules
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
                "note_tp": note.note_tp,
                "note_rattrapage": note.note_rattrapage,
                "note_finale": note.note_finale,
                "note_sur_20": float(note.note_finale) if note and note.note_finale else None,
                "module_has_tp": bool(getattr(note.module, "has_tp", False)),
            })

        return Response(data)

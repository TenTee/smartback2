from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Avg, Q
from rest_framework import viewsets, status as http_status
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Note, Etudiant, Module
from etudiants.models import Inscription
from academique.models import (
    Filiere, Niveau, CourseAssignment, Evaluation, Classe, AnneeAcademique, Affectation,
)
from .serializers import NoteSerializer, NoteSummarySerializer, NoteFiliereSerializer
from academique.middleware import get_current_academic_year_id


def _to_decimal(value):
    if value is None or value == "" or value == "null":
        return None
    try:
        d = Decimal(str(value))
        if d < 0:
            d = Decimal("0")
        if d > 20:
            d = Decimal("20")
        return d
    except (InvalidOperation, ValueError, TypeError):
        return None


class NoteViewSet(viewsets.ModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'etudiant', 'etudiant__filiere', 'module', 'classe', 'evaluation'
        )

        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(
                Q(annee_academique_ref_id=year_id) |
                Q(annee_academique_ref__isnull=True, classe__annee_academique_id=year_id) |
                Q(annee_academique_ref__isnull=True, classe__isnull=True)
            )

        classe_id = self.request.query_params.get("classe")
        evaluation_id = self.request.query_params.get("evaluation")

        if self.request.user.is_authenticated and getattr(self.request.user, 'role', '') == 'etudiant':
            etudiant = getattr(self.request.user, 'etudiant_profile', None)
            if etudiant:
                queryset = queryset.filter(etudiant=etudiant)

        if classe_id:
            queryset = queryset.filter(classe_id=classe_id)
        if evaluation_id:
            queryset = queryset.filter(evaluation_id=evaluation_id)
        return queryset

    def get_serializer_class(self):
        if self.action == "list" and self.request.query_params.get("summary") == "true":
            return NoteSummarySerializer
        return NoteSerializer

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil étudiant introuvable"}, status=404)

        session = request.query_params.get("session")
        notes = Note.objects.filter(etudiant=etudiant)

        year_id = get_current_academic_year_id()
        if year_id:
            notes = notes.filter(
                Q(annee_academique_ref_id=year_id) |
                Q(classe__annee_academique_id=year_id)
            )

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

    def list(self, request, *args, **kwargs):
        if request.query_params.get("summary") == "true":
            year_id = get_current_academic_year_id()
            notes_qs = Note.objects.all()
            if year_id:
                notes_qs = notes_qs.filter(
                    Q(annee_academique_ref_id=year_id) |
                    Q(classe__annee_academique_id=year_id)
                )

            rows = (
                notes_qs.values(
                    "etudiant_id",
                    "etudiant__nom",
                    "etudiant__matricule",
                    "etudiant__filiere__nom",
                    "session"
                )
                .distinct()
            )

            data = []
            for n in rows:
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
            filiere = Filiere.objects.get(pk=filiere_id)
        except Filiere.DoesNotExist:
            return Response({"error": "Filière introuvable"}, status=404)

        niveaux = Niveau.objects.filter(cycle__filiere=filiere)

        data = {
            "filiere_id": filiere.id,
            "filiere_nom": filiere.nom,
            "session": session,
            "niveaux": []
        }

        for niveau in niveaux:
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
                evaluation = Evaluation.objects.select_related('classe', 'module').get(pk=evaluation_id)
                classe = evaluation.classe
                module = evaluation.module
            except Evaluation.DoesNotExist:
                return Response({"error": "Évaluation introuvable"}, status=404)
        elif classe_id and module_id:
            try:
                classe = Classe.objects.select_related('filiere', 'cycle', 'niveau').get(pk=classe_id)
                module = Module.objects.get(pk=module_id)
                evaluation = None
            except (Classe.DoesNotExist, Module.DoesNotExist):
                return Response({"error": "Classe ou Module introuvable"}, status=404)
        else:
            return Response({"error": "Paramètres manquants (evaluation ou classe+module)"}, status=400)

        # Formateur assigné à ce module pour cette classe
        formateur_nom = ""
        affectation = Affectation.objects.filter(
            module=module,
            classe=classe,
        ).select_related('enseignant').first()
        if affectation and affectation.enseignant:
            formateur_nom = affectation.enseignant.nom or ""

        # All students enrolled in this class
        inscriptions = Inscription.objects.filter(classe=classe).select_related('etudiant')

        data = []
        for ins in inscriptions:
            etudiant = ins.etudiant
            # Look for existing note
            note_query = Note.objects.filter(etudiant=etudiant, module=module)
            if evaluation:
                note_query = note_query.filter(evaluation=evaluation)
            else:
                note_query = note_query.filter(
                    Q(classe=classe) | Q(classe__isnull=True)
                )

            note = note_query.first()

            data.append({
                "etudiant_id": etudiant.id,
                "etudiant_nom": etudiant.nom,
                "etudiant_matricule": getattr(etudiant, 'matricule', '') or '',
                "classe_id": classe.id,
                "module_id": module.id,
                "evaluation_id": evaluation.id if evaluation else None,
                "formateur_nom": formateur_nom,
                "note_id": note.id if note else None,
                "note_cc": float(note.note_cc) if note and note.note_cc is not None else None,
                "note_sn": float(note.note_sn) if note and note.note_sn is not None else None,
                "note_rattrapage": float(note.note_rattrapage) if note and note.note_rattrapage is not None else None,
                "note_finale": float(note.note_finale) if note and note.note_finale is not None else None,
            })

        return Response(data)

    @action(detail=False, methods=["post"], url_path="batch-save")
    def batch_save(self, request):
        notes_data = request.data.get("notes", [])
        if not notes_data:
            return Response({"error": "Aucune donnée fournie"}, status=400)

        errors = []
        results = []

        with transaction.atomic():
            for idx, item in enumerate(notes_data):
                etudiant_id = item.get("etudiant_id")
                module_id = item.get("module_id")
                classe_id = item.get("classe_id")
                evaluation_id = item.get("evaluation_id") or None

                if not etudiant_id or not module_id:
                    errors.append(f"Ligne {idx+1}: etudiant_id et module_id requis")
                    continue

                note_cc = _to_decimal(item.get("note_cc"))
                note_sn = _to_decimal(item.get("note_sn"))
                note_rattrapage = _to_decimal(item.get("note_rattrapage"))

                # Skip rows where nothing is entered
                if note_cc is None and note_sn is None and note_rattrapage is None:
                    continue

                # Lookup existing note
                filter_kwargs = {
                    "etudiant_id": etudiant_id,
                    "module_id": module_id,
                }
                if evaluation_id:
                    filter_kwargs["evaluation_id"] = evaluation_id
                else:
                    filter_kwargs["classe_id"] = classe_id

                existing = Note.objects.filter(**filter_kwargs).first()

                if existing:
                    existing.note_cc = note_cc
                    existing.note_sn = note_sn
                    existing.note_rattrapage = note_rattrapage
                    if classe_id:
                        existing.classe_id = classe_id
                    existing.save()
                    results.append(existing)
                else:
                    note = Note(
                        etudiant_id=etudiant_id,
                        module_id=module_id,
                        classe_id=classe_id,
                        evaluation_id=evaluation_id,
                        note_cc=note_cc,
                        note_sn=note_sn,
                        note_rattrapage=note_rattrapage,
                    )
                    note.save()
                    results.append(note)

        response_data = NoteSerializer(results, many=True).data
        resp = {"message": f"{len(results)} notes enregistrées", "data": response_data}
        if errors:
            resp["warnings"] = errors
        return Response(resp, status=http_status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="details")
    def details(self, request, pk=None):
        session = request.query_params.get("session")

        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Étudiant introuvable"}, status=404)

        notes = Note.objects.filter(etudiant=etudiant).select_related("module", "classe")

        year_id = get_current_academic_year_id()
        if year_id:
            notes = notes.filter(
                Q(annee_academique_ref_id=year_id) |
                Q(classe__annee_academique_id=year_id)
            )

        if session:
            notes = notes.filter(session=session)

        data = []
        for note in notes:
            data.append({
                "id": note.id,
                "etudiant_id": etudiant.id,
                "session": note.session,
                "module_id": note.module.id,
                "module_nom": note.module.nom,
                "module_semestre": getattr(note.module, 'semestre', '') or note.session,
                "classe_id": note.classe_id,
                "classe_nom": note.classe.nom if note.classe else "",
                "formateur_nom": "",
                "note_cc": float(note.note_cc) if note.note_cc is not None else None,
                "note_sn": float(note.note_sn) if note.note_sn is not None else None,
                "note_rattrapage": float(note.note_rattrapage) if note.note_rattrapage is not None else None,
                "note_finale": float(note.note_finale) if note.note_finale is not None else None,
                "note_sur_20": float(note.note_finale) if note.note_finale is not None else None,
            })

        return Response(data)

    @action(detail=True, methods=["get"], url_path="releve-notes")
    def releve_notes(self, request, pk=None):
        """Endpoint dédié pour générer le relevé de notes complet d'un étudiant (les 2 semestres)."""
        try:
            etudiant = Etudiant.objects.get(pk=pk)
        except Etudiant.DoesNotExist:
            return Response({"error": "Étudiant introuvable"}, status=404)

        inscription = Inscription.objects.filter(
            etudiant=etudiant,
            classe__isnull=False,
        ).select_related(
            'classe__filiere', 'classe__cycle', 'classe__niveau', 'classe__annee_academique'
        ).order_by('-date_inscription').first()

        from academique.models import ConfigurationEtablissement, ParametresGlobaux
        config = ConfigurationEtablissement.get_config()
        params = ParametresGlobaux.get_parametres()

        notes_qs = Note.objects.filter(etudiant=etudiant).select_related("module", "classe")

        year_id = get_current_academic_year_id()
        if year_id:
            notes_qs = notes_qs.filter(
                Q(annee_academique_ref_id=year_id) |
                Q(classe__annee_academique_id=year_id)
            )

        photo_doc = None
        try:
            from etudiants.models import EtudiantDocument
            photo_doc = EtudiantDocument.objects.filter(
                etudiant=etudiant, type_document__icontains="Photo"
            ).order_by('-date_upload').first()
        except Exception:
            pass

        def get_grade(note_finale):
            if note_finale is None:
                return "-"
            n = float(note_finale)
            if n >= 16:
                return "A"
            elif n >= 14:
                return "B+"
            elif n >= 12:
                return "B"
            elif n >= 10:
                return "C+"
            elif n >= 8:
                return "C"
            elif n >= 6:
                return "D"
            return "F"

        def get_observation(note_finale):
            if note_finale is None:
                return "-"
            n = float(note_finale)
            if n >= 16:
                return "Excellent"
            elif n >= 14:
                return "Très Bien"
            elif n >= 12:
                return "Bien"
            elif n >= 10:
                return "Passable"
            return "Non validé"

        def get_mention(moyenne):
            if moyenne is None:
                return "-"
            if moyenne >= 16:
                return "Très Bien"
            elif moyenne >= 14:
                return "Bien"
            elif moyenne >= 12:
                return "Assez Bien"
            elif moyenne >= 10:
                return "Passable"
            return "Échec"

        def compute_semester_data(semester_notes):
            notes_list = []
            total_credits = 0
            credits_obtenus = 0
            credits_valides = 0
            total_points_weighted = 0.0
            total_coeff = 0

            for note in semester_notes:
                module = note.module
                credits = getattr(module, 'credits', 3) or 3
                coeff = getattr(module, 'coefficient', 1) or 1
                note_finale = float(note.note_finale) if note.note_finale is not None else None

                total_credits += credits
                if note_finale is not None:
                    credits_obtenus += credits
                    if note_finale >= 10:
                        credits_valides += credits
                    total_points_weighted += note_finale * coeff
                    total_coeff += coeff

                notes_list.append({
                    "id": note.id,
                    "code_ue": getattr(module, 'code_ue', '') or '',
                    "module_nom": module.nom,
                    "credits": credits,
                    "note_cc": float(note.note_cc) if note.note_cc is not None else None,
                    "note_sn": float(note.note_sn) if note.note_sn is not None else None,
                    "note_finale": note_finale,
                    "grade": get_grade(note.note_finale),
                    "observation": get_observation(note.note_finale),
                })

            moyenne = round(total_points_weighted / total_coeff, 2) if total_coeff > 0 else None
            return {
                "notes": notes_list,
                "moyenne": moyenne,
                "total_credits": total_credits,
                "credits_obtenus": credits_obtenus,
                "credits_valides": credits_valides,
            }

        semestres_data = []
        global_credits = 0
        global_credits_obtenus = 0
        global_credits_valides = 0
        global_points = 0.0
        global_coeff = 0

        for session_label in ["Semestre 1", "Semestre 2"]:
            sem_notes = notes_qs.filter(session=session_label)
            if not sem_notes.exists():
                continue
            sem_data = compute_semester_data(sem_notes)
            sem_data["session"] = session_label
            semestres_data.append(sem_data)

            global_credits += sem_data["total_credits"]
            global_credits_obtenus += sem_data["credits_obtenus"]
            global_credits_valides += sem_data["credits_valides"]
            for note in sem_notes:
                if note.note_finale is not None:
                    coeff = getattr(note.module, 'coefficient', 1) or 1
                    global_points += float(note.note_finale) * coeff
                    global_coeff += coeff

        moyenne_annuelle = round(global_points / global_coeff, 2) if global_coeff > 0 else None

        effectif = 0
        rang = None
        if inscription and inscription.classe_id:
            classe_etudiants = list(Inscription.objects.filter(
                classe=inscription.classe
            ).values_list('etudiant_id', flat=True))
            effectif = len(classe_etudiants)

            moyennes_classe = []
            for etu_id in classe_etudiants:
                etu_notes = Note.objects.filter(etudiant_id=etu_id).select_related("module")
                if year_id:
                    etu_notes = etu_notes.filter(
                        Q(annee_academique_ref_id=year_id) |
                        Q(classe__annee_academique_id=year_id)
                    )
                tp = 0.0
                tc = 0
                for n in etu_notes:
                    if n.note_finale is not None:
                        c = getattr(n.module, 'coefficient', 1) or 1
                        tp += float(n.note_finale) * c
                        tc += c
                moy = round(tp / tc, 2) if tc > 0 else 0
                moyennes_classe.append({"etudiant_id": etu_id, "moyenne": moy})

            moyennes_classe.sort(key=lambda x: -x["moyenne"])
            for idx, item in enumerate(moyennes_classe, start=1):
                if item["etudiant_id"] == etudiant.id:
                    rang = idx
                    break

        annee_academique = ""
        if inscription and inscription.classe:
            annee_academique = inscription.classe.annee_academique.libelle
        elif notes_qs.exists():
            annee_academique = notes_qs.first().annee_academique

        response_data = {
            "etablissement": {
                "nom": config.nom,
                "logo": config.logo.url if config.logo else None,
                "logo_entete": config.logo_entete.url if config.logo_entete else None,
                "adresse": config.adresse,
                "ville": config.ville,
                "telephone": config.telephone,
                "email": config.email,
                "site_web": config.site_web,
                "couleur_primaire": config.couleur_primaire,
                "couleur_secondaire": config.couleur_secondaire,
                "slogan": getattr(config, 'slogan', ''),
                "nom_directeur": config.nom_directeur,
                "titre_directeur": config.titre_directeur,
                "signature_directeur": config.signature_directeur.url if config.signature_directeur else None,
            },
            "etudiant": {
                "id": etudiant.id,
                "nom": etudiant.nom,
                "matricule": etudiant.matricule,
                "date_naissance": etudiant.date_naissance.strftime("%d/%m/%Y") if etudiant.date_naissance else "",
                "filiere": etudiant.filiere.nom if etudiant.filiere_id else "",
                "niveau": inscription.niveau.nom if inscription else "",
                "classe": inscription.classe.nom if inscription and inscription.classe else "",
                "photo": photo_doc.fichier.url if photo_doc else None,
            },
            "parametres": {
                "pourcentage_cc": params.pourcentage_cc,
                "pourcentage_sn": params.pourcentage_sn,
                "annee_academique": annee_academique,
            },
            "semestres": semestres_data,
            "resume": {
                "moyenne_annuelle": moyenne_annuelle,
                "credits_obtenus": global_credits_obtenus,
                "total_credits": global_credits,
                "credits_valides": global_credits_valides,
                "rang": rang,
                "effectif": effectif,
                "mention": get_mention(moyenne_annuelle),
            },
        }

        return Response(response_data)

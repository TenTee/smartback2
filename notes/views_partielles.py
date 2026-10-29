from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import EvaluationPartielle, NotePartielle
from .partielles import composantes_calculees, recalculer


def _peut_saisir(user, classe_id, module_id):
    """Formateur du module dans la classe (affectation / emploi du temps) ou personnel pédagogique."""
    from notifications.services import droit, profil
    p = profil(user)
    if p == "formateur":
        from messagerie.acces import formateurs_de
        return formateurs_de(classe_id, module_id).filter(pk=user.formateur_profile.pk).exists()
    if p == "personnel":
        return droit(user, "pedagogie") == "ecriture"
    return False


def _evaluation_json(e, notes=None):
    return {
        "id": e.id, "classe": e.classe_id, "module": e.module_id, "composante": e.composante,
        "composante_libelle": e.get_composante_display(), "libelle": e.libelle,
        "coefficient": float(e.coefficient), "date": e.date, "ordre": e.ordre,
        "notes": notes if notes is not None else {
            str(n.etudiant_id): (float(n.valeur) if n.valeur is not None else None) for n in e.notes.all()
        },
    }


class EvaluationPartielleViewSet(viewsets.ViewSet):
    """Évaluations partielles d'une classe pour un module (saisie formateur).

    GET    /api/evaluations-partielles/?classe=&module=
    POST   /api/evaluations-partielles/                  {classe, module, composante: cc|sn, libelle, coefficient?, date?}
    PATCH  /api/evaluations-partielles/{id}/             {libelle?, coefficient?, date?, composante?}
    DELETE /api/evaluations-partielles/{id}/
    POST   /api/evaluations-partielles/{id}/notes/       {notes: [{etudiant_id, valeur}]}
    La CC (ou la SN) devient la moyenne pondérée des évaluations de la composante.
    """

    def _verifier(self, classe_id, module_id):
        if not _peut_saisir(self.request.user, classe_id, module_id):
            raise PermissionDenied("Vous n'enseignez pas ce cours dans cette classe.")

    def _get(self, pk):
        e = get_object_or_404(EvaluationPartielle.objects.select_related("classe", "module"), pk=pk)
        self._verifier(e.classe_id, e.module_id)
        return e

    def list(self, request):
        classe_id, module_id = request.query_params.get("classe"), request.query_params.get("module")
        if not (classe_id and module_id):
            raise ValidationError({"detail": "classe et module sont requis."})
        self._verifier(int(classe_id), int(module_id))
        evals = EvaluationPartielle.objects.filter(classe_id=classe_id, module_id=module_id).prefetch_related("notes")
        return Response({
            "evaluations": [_evaluation_json(e) for e in evals],
            "calcule": composantes_calculees(classe_id, module_id),
        })

    def create(self, request):
        from academique.models import Classe
        from modules.models import Module
        d = request.data
        classe = get_object_or_404(Classe, pk=d.get("classe"))
        module = get_object_or_404(Module, pk=d.get("module"))
        self._verifier(classe.id, module.id)
        comp = d.get("composante")
        if comp not in ("cc", "sn"):
            raise ValidationError({"composante": ["Choisissez CC ou SN."]})
        libelle = str(d.get("libelle") or "").strip()
        if not libelle:
            n = EvaluationPartielle.objects.filter(classe=classe, module=module, composante=comp).count() + 1
            libelle = f"{'Évaluation' if comp == 'cc' else 'Épreuve'} {n}"
        try:
            coef = float(d.get("coefficient") or 1)
        except (TypeError, ValueError):
            raise ValidationError({"coefficient": ["Coefficient invalide."]})
        if coef <= 0 or coef > 99:
            raise ValidationError({"coefficient": ["Le coefficient doit être compris entre 0 et 99."]})
        formateur = getattr(request.user, "formateur_profile", None) if hasattr(request.user, "formateur_profile") else None
        ordre = EvaluationPartielle.objects.filter(classe=classe, module=module, composante=comp).count()
        e = EvaluationPartielle.objects.create(
            classe=classe, module=module, composante=comp, libelle=libelle[:120], coefficient=coef,
            date=d.get("date") or None, ordre=ordre, formateur=formateur,
        )
        return Response(_evaluation_json(e, {}), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        e = self._get(pk)
        d = request.data
        if "libelle" in d and str(d["libelle"]).strip():
            e.libelle = str(d["libelle"]).strip()[:120]
        if "coefficient" in d:
            try:
                coef = float(d["coefficient"])
            except (TypeError, ValueError):
                raise ValidationError({"coefficient": ["Coefficient invalide."]})
            if coef <= 0 or coef > 99:
                raise ValidationError({"coefficient": ["Le coefficient doit être compris entre 0 et 99."]})
            e.coefficient = coef
        if "date" in d:
            e.date = d["date"] or None
        if d.get("composante") in ("cc", "sn"):
            e.composante = d["composante"]
        with transaction.atomic():
            e.save()
            recalculer(e.classe, e.module)
        return Response(_evaluation_json(e))

    def destroy(self, request, pk=None):
        e = self._get(pk)
        classe, module = e.classe, e.module
        with transaction.atomic():
            e.delete()
            recalculer(classe, module)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        e = self._get(pk)
        items = request.data.get("notes") or []
        from etudiants.models import Inscription
        inscrits = set(Inscription.objects.filter(classe=e.classe).values_list("etudiant_id", flat=True))
        erreurs, touches = [], set()
        with transaction.atomic():
            for it in items:
                try:
                    etu = int(it.get("etudiant_id"))
                except (TypeError, ValueError):
                    continue
                if etu not in inscrits:
                    erreurs.append(f"Étudiant {etu} non inscrit dans la classe.")
                    continue
                v = it.get("valeur")
                if v in ("", None):
                    v = None
                else:
                    try:
                        v = round(float(str(v).replace(",", ".")), 2)
                    except ValueError:
                        erreurs.append(f"Note invalide pour l'étudiant {etu}.")
                        continue
                    if v < 0 or v > 20:
                        erreurs.append(f"La note doit être entre 0 et 20 (étudiant {etu}).")
                        continue
                NotePartielle.objects.update_or_create(evaluation=e, etudiant_id=etu, defaults={"valeur": v})
                touches.add(etu)
            maj = recalculer(e.classe, e.module, touches) if touches else 0
        return Response({"enregistrees": len(touches), "notes_mises_a_jour": maj, "erreurs": erreurs,
                         "evaluation": _evaluation_json(EvaluationPartielle.objects.prefetch_related("notes").get(pk=e.pk))})

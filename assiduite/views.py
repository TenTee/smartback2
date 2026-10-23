from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AssiduiteRecord
from .serializers import AssiduiteRecordSerializer
from academique.middleware import get_current_academic_year_id


class AssiduiteRecordViewSet(viewsets.ModelViewSet):
    serializer_class = AssiduiteRecordSerializer
    queryset = AssiduiteRecord.objects.all()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return AssiduiteRecord.objects.none()

        queryset = AssiduiteRecord.objects.all()
        
        year_id = get_current_academic_year_id()
        if year_id:
            queryset = queryset.filter(etudiant__inscriptions__annee_academique_ref_id=year_id)
        
        # Si c'est un étudiant, on restreint à ses propres records
        if hasattr(user, 'etudiant_profile'):
            queryset = queryset.filter(etudiant=user.etudiant_profile)

        params = self.request.query_params

        etudiant_id = params.get("etudiant")
        filiere_id = params.get("filiere")
        niveau_id = params.get("niveau")
        module_id = params.get("module")
        type_value = params.get("type")
        date_from = params.get("date_from")
        date_to = params.get("date_to")

        if etudiant_id:
            queryset = queryset.filter(etudiant_id=etudiant_id)
        if filiere_id:
            queryset = queryset.filter(etudiant__filiere_id=filiere_id)
        if niveau_id:
            queryset = queryset.filter(etudiant__inscriptions__niveau_id=niveau_id)
        if module_id:
            queryset = queryset.filter(module_id=module_id)
        if type_value:
            queryset = queryset.filter(type=type_value)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset.distinct()

    @action(detail=False, methods=["get"], url_path="seances-du-jour")
    def seances_du_jour(self, request):
        """Cours programmés pour la classe de l'étudiant à une date : ?etudiant=&date=YYYY-MM-DD"""
        from django.utils.dateparse import parse_date
        from etudiants.models import Etudiant
        from .seances_jour import seances_du_jour

        jour = parse_date(request.query_params.get("date") or "")
        try:
            etudiant = Etudiant.objects.get(pk=request.query_params.get("etudiant"))
        except (Etudiant.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "Étudiant introuvable."}, status=404)
        if not jour:
            return Response({"detail": "Date invalide."}, status=400)
        classe, seances = seances_du_jour(etudiant, jour, get_current_academic_year_id())
        deja = {}
        for r in AssiduiteRecord.objects.filter(etudiant=etudiant, date=jour, emploi__isnull=False):
            deja[r.emploi_id] = {"id": r.id, "type": r.type}
        return Response({
            "date": jour,
            "classe_id": classe.id if classe else None,
            "classe_nom": classe.nom if classe else None,
            "seances": [{
                "emploi_id": e.id,
                "heure_debut": e.heure_debut,
                "heure_fin": e.heure_fin,
                "module_id": e.module_id,
                "module_nom": e.module.nom,
                "formateur_nom": e.formateur.nom if e.formateur_id else "",
                "salle_nom": e.salle.nom if e.salle_id else "",
                "deja": deja.get(e.id),
            } for e in seances],
        })

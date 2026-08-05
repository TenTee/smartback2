from rest_framework import viewsets
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

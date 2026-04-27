from rest_framework import viewsets
from .models import AssiduiteRecord
from .serializers import AssiduiteRecordSerializer


class AssiduiteRecordViewSet(viewsets.ModelViewSet):
    serializer_class = AssiduiteRecordSerializer
    queryset = AssiduiteRecord.objects.all()

    def get_queryset(self):
        queryset = AssiduiteRecord.objects.all()
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

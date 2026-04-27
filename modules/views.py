from rest_framework import generics
from rest_framework.exceptions import ValidationError
from django.db.models import ProtectedError

from .models import Module
from .serializers import ModuleSerializer

class ModuleListCreateView(generics.ListCreateAPIView):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

class ModuleRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                "Impossible de supprimer ce module car il est utilisé par des évaluations ou des affectations."
            )

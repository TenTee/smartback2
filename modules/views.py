from rest_framework import generics
from rest_framework.exceptions import ValidationError
from django.db.models import ProtectedError

from .models import Module
from .serializers import ModuleSerializer

class ModuleListCreateView(generics.ListCreateAPIView):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

    def perform_create(self, serializer):
        module = serializer.save()
        classe_id = self.request.data.get('classe')
        if isinstance(classe_id, list):
            classe_id = classe_id[0] if classe_id else None
        if classe_id:
            from academique.models import Classe
            try:
                classe = Classe.objects.get(id=classe_id)
                classe.modules.add(module)
            except (Classe.DoesNotExist, ValueError, TypeError):
                pass

class ModuleRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

    def perform_update(self, serializer):
        module = serializer.save()
        classe_id = self.request.data.get('classe')
        if isinstance(classe_id, list):
            classe_id = classe_id[0] if classe_id else None
        if classe_id:
            from academique.models import Classe
            try:
                classe = Classe.objects.get(id=classe_id)
                classe.modules.add(module)
            except (Classe.DoesNotExist, ValueError, TypeError):
                pass

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                "Impossible de supprimer ce module car il est utilisé par des évaluations ou des affectations."
            )

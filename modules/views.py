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
        classe_ids = self.request.data.get('classe')
        if not isinstance(classe_ids, list):
            classe_ids = [classe_ids] if classe_ids else []
        from academique.models import Classe
        for cid in classe_ids:
            try:
                classe = Classe.objects.get(id=cid)
                classe.modules.add(module)
            except (Classe.DoesNotExist, ValueError, TypeError):
                pass

class ModuleRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

    def perform_update(self, serializer):
        module = serializer.save()
        from academique.models import Classe

        for old_classe in Classe.objects.filter(modules=module):
            old_classe.modules.remove(module)

        classe_ids = self.request.data.get('classe')
        if not isinstance(classe_ids, list):
            classe_ids = [classe_ids] if classe_ids else []
        for cid in classe_ids:
            try:
                classe = Classe.objects.get(id=cid)
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

from rest_framework import viewsets, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Inventaire
from .serializers import InventaireSerializer

class InventaireViewSet(viewsets.ModelViewSet):
    queryset = Inventaire.objects.all()
    serializer_class = InventaireSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["categorie", "statut"]

    def create(self, request, *args, **kwargs):
        quantite = int(request.data.get("quantite", 1))
        articles = []

        # ✅ enlever quantite des données envoyées au modèle
        data = request.data.copy()
        data.pop("quantite", None)

        for i in range(quantite):
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            articles.append(serializer.data)

        headers = self.get_success_headers(serializer.data)
        return Response(articles, status=status.HTTP_201_CREATED, headers=headers)
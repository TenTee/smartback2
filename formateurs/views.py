# formateurs/views.py
from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from .models import Formateur
from .serializers import FormateurSerializer

class FormateurListCreateView(generics.ListCreateAPIView):
    queryset = Formateur.objects.all()
    serializer_class = FormateurSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["specialites"]  # ✅ permet de filtrer par ID du module

class FormateurRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Formateur.objects.all()
    serializer_class = FormateurSerializer
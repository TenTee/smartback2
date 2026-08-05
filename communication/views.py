from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import Communication
from .serializers import CommunicationSerializer

class CommunicationListCreate(generics.ListCreateAPIView):
    queryset = Communication.objects.all()
    serializer_class = CommunicationSerializer
    permission_classes = [IsAuthenticated]  # tu peux ajouter IsAdminOrReadOnly si besoin

class CommunicationDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = Communication.objects.all()
    serializer_class = CommunicationSerializer
    permission_classes = [IsAuthenticated]

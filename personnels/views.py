from rest_framework import generics
from .models import Personnel
from .serializers import PersonnelSerializer

class PersonnelListCreateView(generics.ListCreateAPIView):
    queryset = Personnel.objects.all()
    serializer_class = PersonnelSerializer


class PersonnelDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Personnel.objects.all()
    serializer_class = PersonnelSerializer


from rest_framework import viewsets
from .models import Conge
from .serializers import CongeSerializer

class CongeViewSet(viewsets.ModelViewSet):
    queryset = Conge.objects.all()
    serializer_class = CongeSerializer
   
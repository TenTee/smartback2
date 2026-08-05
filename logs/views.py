from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Log
from .serializers import LogSerializer

class LogViewSet(viewsets.ModelViewSet):
    queryset = Log.objects.all()
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated]  # ou [] si pas besoin d'authentification

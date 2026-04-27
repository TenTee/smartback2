from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType

from .models import Paie
from .serializers import PaieSerializer

class PaieViewSet(viewsets.ModelViewSet):
    """
    CRUD pour les paies
    """
    queryset = Paie.objects.all().order_by('-date')
    serializer_class = PaieSerializer


class ContentTypeView(APIView):
    """
    Expose les IDs ContentType pour Personnel et Formateur
    """
    def get(self, request):
        return Response({
            "personnel": ContentType.objects.get(app_label="paie", model="personnel").id,
            "formateur": ContentType.objects.get(app_label="formateurs", model="formateur").id,
        })
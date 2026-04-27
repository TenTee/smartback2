# formations/views.py
from django.db.models.deletion import ProtectedError
from rest_framework import generics, status
from rest_framework.response import Response
from .models import Formation, Niveau
from .serializers import FormationSerializer, NiveauSerializer

class FormationListCreateView(generics.ListCreateAPIView):
    queryset = Formation.objects.all()
    serializer_class = FormationSerializer

class FormationRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Formation.objects.all()
    serializer_class = FormationSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Suppression impossible : cette formation est encore rattachee a une "
                        "filiere academique ou a d'autres donnees dependantes. "
                        "Detachez d'abord la filiere academique concernee."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

class NiveauListCreateView(generics.ListCreateAPIView):
    queryset = Niveau.objects.all()
    serializer_class = NiveauSerializer

class NiveauRetrieveUpdateView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Niveau.objects.all()
    serializer_class = NiveauSerializer

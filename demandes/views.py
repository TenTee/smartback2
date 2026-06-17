# demandes/views.py
from rest_framework import generics
from .models import DemandeArticle
from .serializers import DemandeSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from formateurs.models import Formateur
from personnels.models import Personnel

# 📌 Liste + Création
class DemandeListCreateView(generics.ListCreateAPIView):
    queryset = DemandeArticle.objects.all().order_by("-date_demande")
    serializer_class = DemandeSerializer

# 📌 Récupération + Mise à jour + Suppression
class DemandeRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = DemandeArticle.objects.all()
    serializer_class = DemandeSerializer

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        demande = serializer.save()

        # ✅ Synchronisation demande ↔ article
        if demande.article:
            if demande.statut == "Approuvée":
                demande.article.statut = "Occupée"
            elif demande.statut in ["En attente", "Refusée", "Terminée"]:
                demande.article.statut = "Disponible"
            demande.article.save()

    def perform_destroy(self, instance):
        # ✅ Avant suppression, remettre l'article en Disponible
        if instance.article:
            instance.article.statut = "Disponible"
            instance.article.save()
        instance.delete()

# 📌 Liste combinée des demandeurs (Formateurs + Personnels)
class DemandeursListView(APIView):
    def get(self, request):
        results = []

        # Formateurs
        ct_formateur = ContentType.objects.get_for_model(Formateur)
        for f in Formateur.objects.all():
            results.append({
                "id": f.id,
                "type": "Formateur",
                "nom": str(f),
                "content_type_id": ct_formateur.id,
            })

        # Personnels
        ct_personnel = ContentType.objects.get_for_model(Personnel)
        for p in Personnel.objects.all():
            results.append({
                "id": p.id,
                "type": "Personnel",
                "nom": str(p),
                "content_type_id": ct_personnel.id,
            })

        return Response(results)

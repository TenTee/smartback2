from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.db.models import Count, Q

from .models import DemandeArticle, LigneDemande
from .serializers import (
    DemandeSerializer, DemandeCreateSerializer, DemandeUpdateSerializer,
    LigneDemandeSerializer,
)
from formateurs.models import Formateur
from personnels.models import Personnel
from inventaires.models import Article, Exemplaire, Mouvement


class DemandeListCreateView(generics.ListCreateAPIView):
    queryset = DemandeArticle.objects.prefetch_related("lignes", "lignes__article").all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DemandeCreateSerializer
        return DemandeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        priorite = self.request.query_params.get("priorite")
        if statut:
            qs = qs.filter(statut=statut)
        if priorite:
            qs = qs.filter(priorite=priorite)
        return qs


class DemandeRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = DemandeArticle.objects.prefetch_related("lignes", "lignes__article").all()

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return DemandeUpdateSerializer
        return DemandeSerializer

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)


class DemandeApprouverView(APIView):
    """Approuver une demande et allouer les quantités."""

    def post(self, request, pk):
        try:
            demande = DemandeArticle.objects.get(pk=pk)
        except DemandeArticle.DoesNotExist:
            return Response({"error": "Demande non trouvée"}, status=404)

        if demande.statut not in ["soumise", "en_cours"]:
            return Response({"error": "Cette demande ne peut pas être approuvée"}, status=400)

        lignes_data = request.data.get("lignes", [])
        approbateur_ct = request.data.get("approbateur_content_type")
        approbateur_id = request.data.get("approbateur_object_id")

        for ligne_update in lignes_data:
            try:
                ligne = LigneDemande.objects.get(id=ligne_update["id"], demande=demande)
                ligne.quantite_accordee = ligne_update.get("quantite_accordee", ligne.quantite_demandee)
                ligne.save()
            except LigneDemande.DoesNotExist:
                continue

        demande.statut = "approuvee"
        demande.date_traitement = timezone.now()
        if approbateur_ct and approbateur_id:
            demande.approbateur_content_type_id = approbateur_ct
            demande.approbateur_object_id = approbateur_id
        demande.save()

        return Response(DemandeSerializer(demande).data)


class DemandeLivrerView(APIView):
    """Livrer une demande approuvée : attribuer les exemplaires."""

    def post(self, request, pk):
        try:
            demande = DemandeArticle.objects.get(pk=pk)
        except DemandeArticle.DoesNotExist:
            return Response({"error": "Demande non trouvée"}, status=404)

        if demande.statut != "approuvee":
            return Response({"error": "La demande doit être approuvée avant livraison"}, status=400)

        erreurs = []
        for ligne in demande.lignes.all():
            qte = ligne.quantite_accordee or ligne.quantite_demandee
            exemplaires_dispo = Exemplaire.objects.filter(
                article=ligne.article, statut="en_stock"
            )[:qte]

            if exemplaires_dispo.count() < qte:
                erreurs.append(f"{ligne.article.nom}: seulement {exemplaires_dispo.count()}/{qte} disponibles")
                continue

            for ex in exemplaires_dispo:
                ex.statut = "en_utilisation"
                ex.attributaire_content_type = demande.demandeur_content_type
                ex.attributaire_object_id = demande.demandeur_object_id
                ex.date_attribution = timezone.localdate()
                ex.save()

                Mouvement.objects.create(
                    exemplaire=ex,
                    type_mouvement="sortie",
                    motif=f"Livraison demande {demande.reference}",
                    destinataire_content_type=demande.demandeur_content_type,
                    destinataire_object_id=demande.demandeur_object_id,
                )

        if erreurs:
            return Response({"warnings": erreurs, "message": "Livraison partielle"}, status=200)

        demande.statut = "livree"
        demande.date_livraison = timezone.now()
        demande.save()

        return Response(DemandeSerializer(demande).data)


class DemandeRefuserView(APIView):
    """Refuser une demande avec commentaire."""

    def post(self, request, pk):
        try:
            demande = DemandeArticle.objects.get(pk=pk)
        except DemandeArticle.DoesNotExist:
            return Response({"error": "Demande non trouvée"}, status=404)

        if demande.statut not in ["soumise", "en_cours"]:
            return Response({"error": "Cette demande ne peut pas être refusée"}, status=400)

        demande.statut = "refusee"
        demande.commentaire_refus = request.data.get("commentaire", "")
        demande.date_traitement = timezone.now()
        approbateur_ct = request.data.get("approbateur_content_type")
        approbateur_id = request.data.get("approbateur_object_id")
        if approbateur_ct and approbateur_id:
            demande.approbateur_content_type_id = approbateur_ct
            demande.approbateur_object_id = approbateur_id
        demande.save()

        return Response(DemandeSerializer(demande).data)


class DemandeSoumettreView(APIView):
    """Soumettre un brouillon."""

    def post(self, request, pk):
        try:
            demande = DemandeArticle.objects.get(pk=pk)
        except DemandeArticle.DoesNotExist:
            return Response({"error": "Demande non trouvée"}, status=404)

        if demande.statut != "brouillon":
            return Response({"error": "Seul un brouillon peut être soumis"}, status=400)

        if not demande.lignes.exists():
            return Response({"error": "La demande doit contenir au moins un article"}, status=400)

        demande.statut = "soumise"
        demande.save()
        return Response(DemandeSerializer(demande).data)


class LigneDemandeView(APIView):
    """Ajouter/supprimer des lignes à une demande brouillon."""

    def post(self, request, pk):
        try:
            demande = DemandeArticle.objects.get(pk=pk)
        except DemandeArticle.DoesNotExist:
            return Response({"error": "Demande non trouvée"}, status=404)

        if demande.statut not in ["brouillon", "soumise"]:
            return Response({"error": "Impossible de modifier les articles"}, status=400)

        article_id = request.data.get("article")
        quantite = request.data.get("quantite_demandee", 1)
        notes = request.data.get("notes", "")

        ligne, created = LigneDemande.objects.get_or_create(
            demande=demande, article_id=article_id,
            defaults={"quantite_demandee": quantite, "notes": notes}
        )
        if not created:
            ligne.quantite_demandee = quantite
            ligne.notes = notes
            ligne.save()

        return Response(LigneDemandeSerializer(ligne).data, status=201 if created else 200)

    def delete(self, request, pk):
        try:
            demande = DemandeArticle.objects.get(pk=pk)
        except DemandeArticle.DoesNotExist:
            return Response({"error": "Demande non trouvée"}, status=404)

        ligne_id = request.data.get("ligne_id")
        LigneDemande.objects.filter(id=ligne_id, demande=demande).delete()
        return Response(status=204)


class DemandesStatsView(APIView):
    """Statistiques des demandes."""

    def get(self, request):
        total = DemandeArticle.objects.count()
        par_statut = dict(
            DemandeArticle.objects.values_list("statut").annotate(c=Count("id")).values_list("statut", "c")
        )
        par_priorite = dict(
            DemandeArticle.objects.values_list("priorite").annotate(c=Count("id")).values_list("priorite", "c")
        )

        delai_moyen = None
        traitees = DemandeArticle.objects.filter(date_traitement__isnull=False)
        if traitees.exists():
            from django.db.models import Avg
            from django.db.models.functions import Extract
            delais = [(d.date_traitement - d.date_demande).days for d in traitees[:100]]
            delai_moyen = sum(delais) / len(delais) if delais else 0

        return Response({
            "total": total,
            "par_statut": par_statut,
            "par_priorite": par_priorite,
            "delai_moyen_jours": round(delai_moyen, 1) if delai_moyen else None,
        })


class DemandeursListView(APIView):
    """Liste combinée des demandeurs (Formateurs + Personnels)."""

    def get(self, request):
        results = []
        ct_formateur = ContentType.objects.get_for_model(Formateur)
        for f in Formateur.objects.all():
            results.append({
                "id": f.id,
                "type": "Formateur",
                "nom": str(f),
                "content_type_id": ct_formateur.id,
                "salaire": float(f.salaire) if f.salaire else 0,
            })
        ct_personnel = ContentType.objects.get_for_model(Personnel)
        for p in Personnel.objects.all():
            results.append({
                "id": p.id,
                "type": "Personnel",
                "nom": str(p),
                "content_type_id": ct_personnel.id,
                "salaire": float(p.salaire) if p.salaire else 0,
            })
        return Response(results)

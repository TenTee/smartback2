from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from datetime import timedelta

from .models import Article, Exemplaire, Mouvement, Inventaire
from .serializers import (
    ArticleSerializer, ArticleListSerializer, ArticleCreateSerializer,
    ExemplaireSerializer, MouvementSerializer, InventaireSerializer,
)


class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["categorie"]

    def get_serializer_class(self):
        if self.action == "list":
            return ArticleListSerializer
        if self.action == "create":
            return ArticleCreateSerializer
        return ArticleSerializer

    @action(detail=True, methods=["post"])
    def ajouter_stock(self, request, pk=None):
        """Ajouter des exemplaires à un article existant."""
        article = self.get_object()
        quantite = int(request.data.get("quantite", 1))
        condition = request.data.get("condition", "neuf")
        localisation = request.data.get("localisation", "")
        date_acquisition = request.data.get("date_acquisition", None)

        created = []
        for _ in range(quantite):
            ex = Exemplaire.objects.create(
                article=article,
                statut="en_stock",
                condition=condition,
                localisation=localisation,
                date_acquisition=date_acquisition,
            )
            Mouvement.objects.create(
                exemplaire=ex,
                type_mouvement="entree",
                motif=f"Entrée en stock ({quantite} unités)",
                localisation_destination=localisation,
            )
            created.append(ex)

        article.quantite_totale = article.exemplaires.count()
        article.save(update_fields=["quantite_totale"])

        return Response({
            "message": f"{quantite} exemplaire(s) ajouté(s).",
            "article": ArticleListSerializer(article).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def exemplaires(self, request, pk=None):
        """Lister les exemplaires d'un article."""
        article = self.get_object()
        statut = request.query_params.get("statut")
        qs = article.exemplaires.all()
        if statut:
            qs = qs.filter(statut=statut)
        serializer = ExemplaireSerializer(qs, many=True)
        return Response(serializer.data)


class ExemplaireViewSet(viewsets.ModelViewSet):
    queryset = Exemplaire.objects.select_related("article").all()
    serializer_class = ExemplaireSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["statut", "condition", "article"]

    @action(detail=True, methods=["post"])
    def attribuer(self, request, pk=None):
        """Attribuer un exemplaire à un personnel/formateur."""
        exemplaire = self.get_object()
        content_type_id = request.data.get("attributaire_content_type")
        object_id = request.data.get("attributaire_object_id")
        localisation = request.data.get("localisation", "")

        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get(id=content_type_id)

        exemplaire.attributaire_content_type = ct
        exemplaire.attributaire_object_id = object_id
        exemplaire.statut = "en_utilisation"
        exemplaire.date_attribution = timezone.localdate()
        if localisation:
            exemplaire.localisation = localisation
        exemplaire.save()

        Mouvement.objects.create(
            exemplaire=exemplaire,
            type_mouvement="sortie",
            motif=f"Attribution à {exemplaire.attributaire}",
            destinataire_content_type=ct,
            destinataire_object_id=object_id,
            localisation_destination=localisation or exemplaire.localisation,
        )

        return Response(ExemplaireSerializer(exemplaire).data)

    @action(detail=True, methods=["post"])
    def retourner(self, request, pk=None):
        """Retourner un exemplaire en stock."""
        exemplaire = self.get_object()
        localisation = request.data.get("localisation", exemplaire.localisation)
        condition = request.data.get("condition", exemplaire.condition)

        old_attributaire = str(exemplaire.attributaire) if exemplaire.attributaire else "N/A"

        exemplaire.attributaire_content_type = None
        exemplaire.attributaire_object_id = None
        exemplaire.statut = "en_stock"
        exemplaire.date_attribution = None
        exemplaire.condition = condition
        exemplaire.localisation = localisation
        exemplaire.save()

        Mouvement.objects.create(
            exemplaire=exemplaire,
            type_mouvement="retour",
            motif=f"Retour de {old_attributaire}",
            localisation_destination=localisation,
        )

        return Response(ExemplaireSerializer(exemplaire).data)

    @action(detail=True, methods=["post"])
    def changer_statut(self, request, pk=None):
        """Changer le statut d'un exemplaire (maintenance, panne, réforme)."""
        exemplaire = self.get_object()
        nouveau_statut = request.data.get("statut")
        motif = request.data.get("motif", "")

        type_map = {
            "en_maintenance": "maintenance",
            "en_panne": "maintenance",
            "reforme": "reforme",
            "en_stock": "retour",
        }

        if nouveau_statut not in dict(Exemplaire.STATUTS):
            return Response({"error": "Statut invalide"}, status=400)

        exemplaire.statut = nouveau_statut
        if nouveau_statut in ["reforme", "en_panne", "en_maintenance"]:
            exemplaire.attributaire_content_type = None
            exemplaire.attributaire_object_id = None
            exemplaire.date_attribution = None
        exemplaire.save()

        Mouvement.objects.create(
            exemplaire=exemplaire,
            type_mouvement=type_map.get(nouveau_statut, "transfert"),
            motif=motif or f"Changement de statut → {nouveau_statut}",
        )

        return Response(ExemplaireSerializer(exemplaire).data)


class MouvementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Mouvement.objects.select_related("exemplaire", "exemplaire__article").all()
    serializer_class = MouvementSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["type_mouvement", "exemplaire"]


class InventaireStatsView(APIView):
    """Statistiques complètes de l'inventaire."""

    def get(self, request):
        total_articles = Article.objects.count()
        total_exemplaires = Exemplaire.objects.count()
        en_stock = Exemplaire.objects.filter(statut="en_stock").count()
        en_utilisation = Exemplaire.objects.filter(statut="en_utilisation").count()
        en_panne = Exemplaire.objects.filter(statut="en_panne").count()
        en_maintenance = Exemplaire.objects.filter(statut="en_maintenance").count()
        reformes = Exemplaire.objects.filter(statut="reforme").count()

        valeur_stock = Article.objects.aggregate(
            total=Sum(F("prix_unitaire") * F("quantite_totale"))
        )["total"] or 0

        articles_stock_bas = Article.objects.annotate(
            nb_stock=Count("exemplaires", filter=Q(exemplaires__statut="en_stock"))
        ).filter(nb_stock__lte=F("seuil_alerte")).count()

        par_categorie = list(
            Article.objects.values("categorie").annotate(
                nb_articles=Count("id"),
                nb_exemplaires=Count("exemplaires"),
            ).order_by("-nb_exemplaires")
        )

        mouvements_30j = Mouvement.objects.filter(
            date__gte=timezone.now() - timedelta(days=30)
        ).count()

        mouvements_par_type = list(
            Mouvement.objects.filter(
                date__gte=timezone.now() - timedelta(days=30)
            ).values("type_mouvement").annotate(
                count=Count("id")
            ).order_by("-count")
        )

        derniers_mouvements = MouvementSerializer(
            Mouvement.objects.select_related("exemplaire", "exemplaire__article")[:10],
            many=True
        ).data

        # Top articles en utilisation
        top_en_utilisation = list(
            Article.objects.annotate(
                nb_utilisation=Count("exemplaires", filter=Q(exemplaires__statut="en_utilisation"))
            ).filter(nb_utilisation__gt=0).order_by("-nb_utilisation").values(
                "id", "nom", "reference", "nb_utilisation", "quantite_totale"
            )[:10]
        )

        return Response({
            "total_articles": total_articles,
            "total_exemplaires": total_exemplaires,
            "en_stock": en_stock,
            "en_utilisation": en_utilisation,
            "en_panne": en_panne,
            "en_maintenance": en_maintenance,
            "reformes": reformes,
            "valeur_stock": float(valeur_stock),
            "articles_stock_bas": articles_stock_bas,
            "par_categorie": par_categorie,
            "mouvements_30j": mouvements_30j,
            "mouvements_par_type": mouvements_par_type,
            "derniers_mouvements": derniers_mouvements,
            "top_en_utilisation": top_en_utilisation,
        })


# Legacy viewset kept for existing demandes system
class InventaireViewSet(viewsets.ModelViewSet):
    queryset = Inventaire.objects.all()
    serializer_class = InventaireSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["categorie", "statut"]

    def create(self, request, *args, **kwargs):
        quantite = int(request.data.get("quantite", 1))
        articles = []
        data = request.data.copy()
        data.pop("quantite", None)
        for i in range(quantite):
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            articles.append(serializer.data)
        headers = self.get_success_headers(serializer.data)
        return Response(articles, status=status.HTTP_201_CREATED, headers=headers)

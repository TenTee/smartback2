"""Gestion de l'inventaire : localisation (sites, bâtiments, emplacements), matériel suivi à l'unité,
consommables, mouvements, pannes & maintenance, inventaires physiques et tableau de bord."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .acces import DroitLogistique, LectureLogistique, droit_logistique, notifier_logistique, peut_signaler
from .models import (
    Article, Batiment, CampagneInventaire, Constat, Emplacement, Exemplaire, Intervention, Inventaire, Mouvement,
    MouvementStock, Site,
)
from .serializers import (
    ArticleCreateSerializer, ArticleListSerializer, ArticleSerializer, BatimentSerializer, CampagneSerializer,
    ConstatSerializer, EmplacementSerializer, ExemplaireSerializer, InterventionSerializer, InventaireSerializer,
    MouvementSerializer, MouvementStockSerializer, SiteSerializer,
)

ACTIFS = ["en_stock", "en_utilisation", "en_panne", "en_maintenance"]


class PaginationOptionnelle(PageNumberPagination):
    """Pagine seulement si ?page= est fourni (les anciens écrans reçoivent la liste complète)."""
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 5000

    def paginate_queryset(self, queryset, request, view=None):
        if "page" not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


def _mvt(ex, type_, user=None, motif="", source=None, destination=None, **extra):
    return Mouvement.objects.create(
        exemplaire=ex, type_mouvement=type_, motif=motif, utilisateur=user if getattr(user, "is_authenticated", False) else None,
        emplacement_source=source, emplacement_destination=destination,
        localisation_source=str(source)[:200] if source else extra.pop("localisation_source", ""),
        localisation_destination=str(destination)[:200] if destination else extra.pop("localisation_destination", ""),
        **extra,
    )


def _emplacement(valeur):
    if not valeur:
        return None
    return get_object_or_404(Emplacement, pk=valeur)


# ---------------------------------------------------------------------------
# Localisation
# ---------------------------------------------------------------------------
class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [DroitLogistique]

    def get_queryset(self):
        return Site.objects.annotate(
            nb_batiments=Count("batiments", distinct=True), nb_emplacements=Count("emplacements", distinct=True),
            nb_materiels=Count("emplacements__exemplaires", filter=Q(emplacements__exemplaires__statut__in=ACTIFS), distinct=True),
        )

    def destroy(self, request, *args, **kwargs):
        site = self.get_object()
        if site.emplacements.exists():
            site.actif = False
            site.save(update_fields=["actif"])
            return Response({"detail": "Ce site contient des emplacements : il a été désactivé."})
        site.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BatimentViewSet(viewsets.ModelViewSet):
    serializer_class = BatimentSerializer
    permission_classes = [DroitLogistique]

    def get_queryset(self):
        qs = Batiment.objects.select_related("site").annotate(nb_emplacements=Count("emplacements"))
        if self.request.query_params.get("site"):
            qs = qs.filter(site_id=self.request.query_params["site"])
        return qs

    def destroy(self, request, *args, **kwargs):
        b = self.get_object()
        if b.emplacements.exists():
            b.actif = False
            b.save(update_fields=["actif"])
            return Response({"detail": "Ce bâtiment contient des emplacements : il a été désactivé."})
        b.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmplacementViewSet(viewsets.ModelViewSet):
    serializer_class = EmplacementSerializer
    permission_classes = [DroitLogistique]

    def get_queryset(self):
        qs = Emplacement.objects.select_related("site", "batiment", "salle").annotate(
            nb_materiels=Count("exemplaires", filter=Q(exemplaires__statut__in=ACTIFS)))
        p = self.request.query_params
        for champ in ("site", "batiment", "type"):
            if p.get(champ):
                qs = qs.filter(**{champ: p[champ]})
        if p.get("code_qr"):
            qs = qs.filter(code_qr=p["code_qr"])
        if p.get("actifs") in ("1", "true"):
            qs = qs.filter(actif=True)
        if p.get("q"):
            qs = qs.filter(Q(nom__icontains=p["q"]) | Q(code__icontains=p["q"]) | Q(batiment__nom__icontains=p["q"]))
        return qs

    def destroy(self, request, *args, **kwargs):
        e = self.get_object()
        if e.exemplaires.exists() or e.mouvements_entrants.exists():
            e.actif = False
            e.save(update_fields=["actif"])
            return Response({"detail": "Cet emplacement a du matériel ou un historique : il a été désactivé."})
        e.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="importer-salles")
    def importer_salles(self, request):
        """Crée un emplacement pour chaque salle de l'emploi du temps qui n'en a pas encore."""
        from emploidutemps.models import Salle
        site = get_object_or_404(Site, pk=request.data.get("site"))
        batiment = get_object_or_404(Batiment, pk=request.data["batiment"], site=site) if request.data.get("batiment") else None
        crees = 0
        for salle in Salle.objects.filter(emplacement_inventaire__isnull=True):
            Emplacement.objects.create(site=site, batiment=batiment, nom=salle.nom, type="salle", salle=salle)
            crees += 1
        return Response({"crees": crees})

    @action(detail=False, methods=["get"])
    def arbre(self, request):
        """Sites → bâtiments → emplacements, avec le nombre d'équipements et la valeur."""
        empl = list(self.get_queryset().filter(actif=True))
        res = []
        for site in Site.objects.filter(actif=True).prefetch_related("batiments"):
            e_site = [e for e in empl if e.site_id == site.id]
            bats = []
            for b in site.batiments.filter(actif=True):
                e_b = [e for e in e_site if e.batiment_id == b.id]
                bats.append({"id": b.id, "nom": b.nom, "code": b.code, "nb_materiels": sum(e.nb_materiels for e in e_b),
                             "emplacements": EmplacementSerializer(e_b, many=True).data})
            sans = [e for e in e_site if not e.batiment_id]
            res.append({"id": site.id, "nom": site.nom, "adresse": site.adresse, "nb_materiels": sum(e.nb_materiels for e in e_site),
                        "batiments": bats, "emplacements": EmplacementSerializer(sans, many=True).data})
        non_localises = Exemplaire.objects.filter(emplacement__isnull=True, statut__in=ACTIFS).count()
        return Response({"sites": res, "non_localises": non_localises})


# ---------------------------------------------------------------------------
# Articles (catalogue) et consommables
# ---------------------------------------------------------------------------
class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.all()
    permission_classes = [DroitLogistique]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["categorie", "type_article"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Article.objects.all()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(reference__icontains=q) | Q(marque__icontains=q) | Q(modele__icontains=q))
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return ArticleListSerializer
        if self.action == "create":
            return ArticleCreateSerializer
        return ArticleSerializer

    def destroy(self, request, *args, **kwargs):
        a = self.get_object()
        if a.exemplaires.exists() or a.mouvements_stock.exists():
            raise ValidationError({"detail": "Cet article a du matériel ou un historique : il ne peut pas être supprimé."})
        a.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def ajouter_stock(self, request, pk=None):
        """Équipement : crée N exemplaires (avec emplacement, valeur, garantie). Consommable : entrée en stock."""
        article = self.get_object()
        try:
            quantite = int(request.data.get("quantite", 1))
        except (TypeError, ValueError):
            quantite = 0
        if quantite < 1 or quantite > 500:
            raise ValidationError({"quantite": ["Quantité entre 1 et 500."]})
        empl = _emplacement(request.data.get("emplacement"))
        if article.type_article == "consommable":
            with transaction.atomic():
                a = Article.objects.select_for_update().get(pk=article.pk)
                a.stock += quantite
                a.save(update_fields=["stock"])
                MouvementStock.objects.create(article=a, type="entree", quantite=quantite, stock_apres=a.stock, emplacement=empl,
                                              prix_unitaire=request.data.get("prix_unitaire") or None,
                                              motif=str(request.data.get("motif") or "Entrée en stock")[:255], utilisateur=request.user)
            return Response({"message": f"{quantite} {a.unite or 'unité(s)'} ajouté(s).", "article": ArticleListSerializer(a).data},
                            status=status.HTTP_201_CREATED)

        valeur = request.data.get("valeur_achat") or None
        crees = []
        with transaction.atomic():
            for _ in range(quantite):
                ex = Exemplaire.objects.create(
                    article=article, statut="en_stock", condition=request.data.get("condition", "neuf"), emplacement=empl,
                    localisation=request.data.get("localisation", "") if not empl else "",
                    date_acquisition=parse_date(str(request.data.get("date_acquisition") or "")) or None, valeur_achat=valeur,
                    fournisseur=str(request.data.get("fournisseur") or article.fournisseur or "")[:200],
                    numero_facture=str(request.data.get("numero_facture") or "")[:60],
                    date_fin_garantie=parse_date(str(request.data.get("date_fin_garantie") or "")) or None,
                )
                _mvt(ex, "entree", request.user, f"Entrée en stock ({quantite} unité(s))", destination=empl)
                crees.append(ex)
            article.quantite_totale = article.exemplaires.count()
            article.save(update_fields=["quantite_totale"])
        return Response({
            "message": f"{quantite} exemplaire(s) ajouté(s).", "article": ArticleListSerializer(article).data,
            "exemplaires": ExemplaireSerializer(crees, many=True).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mouvement-stock")
    def mouvement_stock(self, request, pk=None):
        """Consommable : sortie (distribution) ou ajustement après comptage."""
        article = self.get_object()
        if article.type_article != "consommable":
            raise ValidationError({"detail": "Réservé aux consommables."})
        type_ = request.data.get("type")
        try:
            quantite = int(request.data.get("quantite"))
        except (TypeError, ValueError):
            raise ValidationError({"quantite": ["Quantité invalide."]})
        if type_ not in ("entree", "sortie", "ajustement") or quantite < 0 or (type_ != "ajustement" and quantite == 0):
            raise ValidationError({"detail": "Type ou quantité invalide."})
        with transaction.atomic():
            a = Article.objects.select_for_update().get(pk=article.pk)
            if type_ == "sortie" and quantite > a.stock:
                raise ValidationError({"quantite": [f"Stock insuffisant : {a.stock} {a.unite} disponible(s)."]})
            a.stock = a.stock + quantite if type_ == "entree" else (a.stock - quantite if type_ == "sortie" else quantite)
            a.save(update_fields=["stock"])
            m = MouvementStock.objects.create(
                article=a, type=type_, quantite=quantite, stock_apres=a.stock, emplacement=_emplacement(request.data.get("emplacement")),
                destinataire=str(request.data.get("destinataire") or "")[:200], prix_unitaire=request.data.get("prix_unitaire") or None,
                motif=str(request.data.get("motif") or "")[:255], utilisateur=request.user,
            )
        if a.stock <= a.seuil_alerte:
            notifier_logistique("stock_bas", f"Stock bas : {a.nom}", f"Il reste {a.stock} {a.unite} (seuil {a.seuil_alerte}).",
                                lien="/inventory/consommables", niveau="alerte")
        return Response({"mouvement": MouvementStockSerializer(m).data, "article": ArticleListSerializer(a).data})

    @action(detail=True, methods=["get"])
    def exemplaires(self, request, pk=None):
        article = self.get_object()
        qs = article.exemplaires.select_related("article", "emplacement__site", "emplacement__batiment")
        if request.query_params.get("statut"):
            qs = qs.filter(statut=request.query_params["statut"])
        return Response(ExemplaireSerializer(qs, many=True).data)


class MouvementStockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MouvementStockSerializer
    permission_classes = [DroitLogistique]
    pagination_class = PaginationOptionnelle

    def get_queryset(self):
        qs = MouvementStock.objects.select_related("article", "emplacement__site", "emplacement__batiment", "utilisateur")
        p = self.request.query_params
        if p.get("article"):
            qs = qs.filter(article_id=p["article"])
        if p.get("type"):
            qs = qs.filter(type=p["type"])
        return qs


# ---------------------------------------------------------------------------
# Matériel (exemplaires)
# ---------------------------------------------------------------------------
class ExemplaireViewSet(viewsets.ModelViewSet):
    serializer_class = ExemplaireSerializer
    permission_classes = [DroitLogistique]
    pagination_class = PaginationOptionnelle

    def get_queryset(self):
        qs = Exemplaire.objects.select_related("article", "emplacement__site", "emplacement__batiment", "attributaire_content_type").annotate(
            nb_pannes_ouvertes=Count("interventions", filter=Q(interventions__statut__in=["signalee", "en_cours"])))
        p = self.request.query_params
        if p.get("statut"):
            qs = qs.filter(statut__in=p["statut"].split(","))
        elif p.get("actifs") in ("1", "true"):
            qs = qs.filter(statut__in=ACTIFS)
        for champ, cle in (("article", "article_id"), ("emplacement", "emplacement_id"), ("condition", "condition"),
                           ("categorie", "article__categorie"), ("site", "emplacement__site_id"), ("batiment", "emplacement__batiment_id")):
            if p.get(champ):
                qs = qs.filter(**{cle: p[champ]})
        if p.get("non_localise") in ("1", "true"):
            qs = qs.filter(emplacement__isnull=True)
        if p.get("attribue") in ("1", "true"):
            qs = qs.filter(attributaire_object_id__isnull=False)
        if p.get("garantie") == "expire_bientot":
            today = timezone.localdate()
            qs = qs.filter(date_fin_garantie__gte=today, date_fin_garantie__lte=today + timedelta(days=60))
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(reference__icontains=q) | Q(numero_serie__icontains=q) | Q(article__nom__icontains=q)
                           | Q(article__marque__icontains=q) | Q(article__modele__icontains=q) | Q(localisation__icontains=q))
        tri = p.get("tri")
        return qs.order_by(tri) if tri in ("reference", "-reference", "article__nom", "-created_at", "emplacement__nom") else qs.order_by("-created_at")

    def perform_update(self, serializer):
        ancien = serializer.instance.emplacement
        ex = serializer.save()
        if ex.emplacement_id != getattr(ancien, "id", None):
            _mvt(ex, "transfert", self.request.user, "Changement d'emplacement (fiche)", source=ancien, destination=ex.emplacement)

    def destroy(self, request, *args, **kwargs):
        ex = self.get_object()
        if ex.mouvements.exclude(type_mouvement="entree").exists() or ex.interventions.exists():
            raise ValidationError({"detail": "Ce matériel a un historique : réformez-le au lieu de le supprimer."})
        article = ex.article
        ex.delete()
        article.quantite_totale = article.exemplaires.count()
        article.save(update_fields=["quantite_totale"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- Scan d'une étiquette (QR) : fiche consultable par le personnel et les formateurs
    @action(detail=False, methods=["get"], url_path="scan")
    def scan(self, request):
        code = (request.query_params.get("code") or "").strip()
        ex = Exemplaire.objects.select_related("article", "emplacement__site", "emplacement__batiment").filter(
            Q(code_qr=code) | Q(reference__iexact=code) | Q(numero_serie__iexact=code)).first() if code else None
        if not ex:
            return Response({"detail": "Aucun matériel ne correspond à ce code."}, status=404)
        gestion = droit_logistique(request.user)
        data = ExemplaireSerializer(ex).data
        if gestion == "none":  # formateur / personnel sans droit : pas de valeurs
            for k in ("valeur_achat", "valeur_origine", "valeur_actuelle", "numero_facture", "fournisseur"):
                data.pop(k, None)
        data["historique"] = MouvementSerializer(ex.mouvements.select_related("utilisateur")[:15], many=True).data
        data["interventions"] = InterventionSerializer(ex.interventions.all()[:10], many=True).data
        data["droit"] = gestion
        data["campagnes"] = [{"id": c.id, "nom": c.nom, "reference": c.reference, "deja_constate": c.constats.filter(exemplaire=ex).exists()}
                             for c in CampagneInventaire.objects.filter(statut="en_cours")]
        return Response(data)

    @action(detail=True, methods=["post"])
    def deplacer(self, request, pk=None):
        ex = self.get_object()
        dest = _emplacement(request.data.get("emplacement"))
        if not dest:
            raise ValidationError({"emplacement": ["Choisissez le nouvel emplacement."]})
        source = ex.emplacement
        ex.emplacement = dest
        ex.save()
        _mvt(ex, "transfert", request.user, str(request.data.get("motif") or "Transfert")[:500], source=source, destination=dest)
        return Response(ExemplaireSerializer(ex).data)

    @action(detail=False, methods=["post"], url_path="deplacer-lot")
    def deplacer_lot(self, request):
        dest = _emplacement(request.data.get("emplacement"))
        ids = request.data.get("exemplaires") or []
        if not dest or not ids:
            raise ValidationError({"detail": "Choisissez le matériel et le nouvel emplacement."})
        n = 0
        with transaction.atomic():
            for ex in Exemplaire.objects.filter(pk__in=ids).select_related("emplacement"):
                source = ex.emplacement
                if source and source.id == dest.id:
                    continue
                ex.emplacement = dest
                ex.save()
                _mvt(ex, "transfert", request.user, str(request.data.get("motif") or "Transfert groupé")[:500], source=source, destination=dest)
                n += 1
        return Response({"deplaces": n})

    @action(detail=True, methods=["post"])
    def attribuer(self, request, pk=None):
        """Attribuer à un membre du personnel / formateur (content type + id)."""
        ex = self.get_object()
        if ex.statut in ("reforme", "perdu"):
            raise ValidationError({"detail": "Ce matériel est réformé ou perdu."})
        try:
            ct = ContentType.objects.get(id=request.data.get("attributaire_content_type"))
        except ContentType.DoesNotExist:
            raise ValidationError({"attributaire_content_type": ["Type d'attributaire inconnu."]})
        object_id = request.data.get("attributaire_object_id")
        dest = _emplacement(request.data.get("emplacement"))
        source = ex.emplacement
        ex.attributaire_content_type, ex.attributaire_object_id = ct, object_id
        ex.statut = "en_utilisation"
        ex.date_attribution = timezone.localdate()
        if dest:
            ex.emplacement = dest
        elif request.data.get("localisation"):
            ex.localisation = request.data["localisation"]
        ex.save()
        _mvt(ex, "sortie", request.user, f"Attribution à {ex.attributaire}", source=source, destination=dest,
             destinataire_content_type=ct, destinataire_object_id=object_id)
        return Response(ExemplaireSerializer(ex).data)

    @action(detail=True, methods=["post"])
    def retourner(self, request, pk=None):
        ex = self.get_object()
        ancien = str(ex.attributaire) if ex.attributaire_object_id and ex.attributaire else "N/A"
        dest = _emplacement(request.data.get("emplacement"))
        source = ex.emplacement
        ex.attributaire_content_type = None
        ex.attributaire_object_id = None
        ex.statut = "en_stock"
        ex.date_attribution = None
        ex.condition = request.data.get("condition", ex.condition)
        if dest:
            ex.emplacement = dest
        elif request.data.get("localisation"):
            ex.localisation = request.data["localisation"]
        ex.save()
        _mvt(ex, "retour", request.user, f"Retour de {ancien}", source=source, destination=dest)
        return Response(ExemplaireSerializer(ex).data)

    @action(detail=True, methods=["post"])
    def changer_statut(self, request, pk=None):
        ex = self.get_object()
        nouveau = request.data.get("statut")
        motif = str(request.data.get("motif") or "")
        if nouveau not in dict(Exemplaire.STATUTS):
            raise ValidationError({"statut": ["Statut invalide."]})
        if nouveau == "reforme" and not motif.strip():
            raise ValidationError({"motif": ["Indiquez le motif de la réforme."]})
        ex.statut = nouveau
        if nouveau in ("reforme", "en_panne", "en_maintenance", "perdu"):
            ex.attributaire_content_type = None
            ex.attributaire_object_id = None
            ex.date_attribution = None
        if nouveau == "reforme":
            ex.date_reforme = timezone.localdate()
            ex.motif_reforme = motif[:255]
        ex.save()
        type_map = {"en_maintenance": "maintenance", "en_panne": "maintenance", "reforme": "reforme", "en_stock": "retour"}
        _mvt(ex, type_map.get(nouveau, "transfert"), request.user, motif or f"Statut → {ex.get_statut_display()}")
        return Response(ExemplaireSerializer(ex).data)


class MouvementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MouvementSerializer
    permission_classes = [DroitLogistique]
    pagination_class = PaginationOptionnelle

    def get_queryset(self):
        qs = Mouvement.objects.select_related("exemplaire", "exemplaire__article", "utilisateur")
        p = self.request.query_params
        if p.get("type_mouvement"):
            qs = qs.filter(type_mouvement__in=p["type_mouvement"].split(","))
        if p.get("exemplaire"):
            qs = qs.filter(exemplaire_id=p["exemplaire"])
        if p.get("emplacement"):
            qs = qs.filter(Q(emplacement_source_id=p["emplacement"]) | Q(emplacement_destination_id=p["emplacement"]))
        if p.get("date_debut"):
            qs = qs.filter(date__date__gte=p["date_debut"])
        if p.get("date_fin"):
            qs = qs.filter(date__date__lte=p["date_fin"])
        if p.get("q"):
            q = p["q"]
            qs = qs.filter(Q(exemplaire__reference__icontains=q) | Q(exemplaire__article__nom__icontains=q) | Q(motif__icontains=q))
        return qs


# ---------------------------------------------------------------------------
# Pannes & maintenance
# ---------------------------------------------------------------------------
class InterventionViewSet(viewsets.ModelViewSet):
    serializer_class = InterventionSerializer
    permission_classes = [DroitLogistique]
    pagination_class = PaginationOptionnelle
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.action == "create":
            return []  # contrôlé dans create : tout personnel / formateur peut signaler une panne
        return super().get_permissions()

    def get_queryset(self):
        qs = Intervention.objects.select_related("exemplaire__article", "exemplaire__emplacement__site", "exemplaire__emplacement__batiment",
                                                 "signale_par", "operation_tresorerie")
        p = self.request.query_params
        if p.get("statut"):
            qs = qs.filter(statut__in=p["statut"].split(","))
        if p.get("ouvertes") in ("1", "true"):
            qs = qs.filter(statut__in=["signalee", "en_cours"])
        if p.get("exemplaire"):
            qs = qs.filter(exemplaire_id=p["exemplaire"])
        if p.get("q"):
            q = p["q"]
            qs = qs.filter(Q(reference__icontains=q) | Q(exemplaire__reference__icontains=q) | Q(exemplaire__article__nom__icontains=q)
                           | Q(description__icontains=q))
        return qs

    def create(self, request, *args, **kwargs):
        if not peut_signaler(request.user):
            return Response({"detail": "Seuls le personnel et les formateurs peuvent signaler une panne."}, status=403)
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ex = ser.validated_data["exemplaire"]
        if ex.statut in ("reforme", "perdu"):
            raise ValidationError({"exemplaire": ["Ce matériel est réformé ou perdu."]})
        if ser.validated_data.get("type", "panne") == "panne" and ex.interventions.filter(type="panne", statut__in=["signalee", "en_cours"]).exists():
            raise ValidationError({"detail": "Une panne est déjà signalée pour ce matériel."})
        with transaction.atomic():
            it = ser.save(signale_par=request.user, statut_precedent=ex.statut)
            if it.type == "panne" and ex.statut not in ("en_panne", "en_maintenance"):
                ex.statut = "en_panne"
                ex.save(update_fields=["statut"])
                _mvt(ex, "maintenance", request.user, f"Panne signalée ({it.reference}) : {it.description[:200]}")
        notifier_logistique("panne_signalee", f"Panne signalée : {ex.article.nom} ({ex.reference})",
                            f"{it.description[:150]} — {ex.emplacement.chemin if ex.emplacement_id else ex.localisation}",
                            lien="/inventory/maintenance", niveau="urgent" if it.priorite == "urgente" else "alerte")
        return Response(self.get_serializer(it).data, status=status.HTTP_201_CREATED)

    def _restaurer(self, it):
        ex = it.exemplaire
        if ex.statut in ("en_panne", "en_maintenance"):
            ex.statut = "en_utilisation" if ex.attributaire_object_id else (
                it.statut_precedent if it.statut_precedent in ("en_stock", "en_utilisation") else "en_stock")
            ex.save(update_fields=["statut"])

    @action(detail=True, methods=["post"])
    def demarrer(self, request, pk=None):
        it = self.get_object()
        if it.statut != "signalee":
            raise ValidationError({"detail": "L'intervention n'est plus au statut « Signalée »."})
        it.statut = "en_cours"
        it.technicien = str(request.data.get("technicien") or it.technicien)[:150]
        it.date_debut = request.data.get("date_debut") or timezone.localdate()
        it.save()
        ex = it.exemplaire
        ex.statut = "en_maintenance"
        ex.save(update_fields=["statut"])
        _mvt(ex, "maintenance", request.user, f"Intervention {it.reference} démarrée{' — ' + it.technicien if it.technicien else ''}")
        return Response(self.get_serializer(it).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        """issue = resolue | irreparable ; cout, resolution ; creer_depense : dépense à approuver en trésorerie ; reformer."""
        it = self.get_object()
        if it.statut not in ("signalee", "en_cours"):
            raise ValidationError({"detail": "Intervention déjà clôturée."})
        issue = request.data.get("issue", "resolue")
        if issue not in ("resolue", "irreparable"):
            raise ValidationError({"issue": ["Valeur invalide."]})
        try:
            cout = Decimal(str(request.data.get("cout") or 0))
        except Exception:  # noqa: BLE001
            raise ValidationError({"cout": ["Montant invalide."]})
        with transaction.atomic():
            it.statut, it.cout = issue, cout
            it.resolution = str(request.data.get("resolution") or "")
            it.technicien = str(request.data.get("technicien") or it.technicien)[:150]
            it.date_debut = it.date_debut or timezone.localdate()
            it.date_fin = request.data.get("date_fin") or timezone.localdate()
            if cout > 0 and str(request.data.get("creer_depense")).lower() in ("1", "true", "oui"):
                it.operation_tresorerie = self._depense(it, request.user)
            it.save()
            ex = it.exemplaire
            if issue == "resolue":
                self._restaurer(it)
                _mvt(ex, "retour", request.user, f"Intervention {it.reference} résolue : {it.resolution[:200]}")
            elif str(request.data.get("reformer")).lower() in ("1", "true", "oui"):
                ex.statut, ex.date_reforme = "reforme", timezone.localdate()
                ex.motif_reforme = f"Irréparable ({it.reference})"
                ex.attributaire_content_type = ex.attributaire_object_id = ex.date_attribution = None
                ex.save()
                _mvt(ex, "reforme", request.user, f"Réformé : irréparable ({it.reference})")
        return Response(self.get_serializer(it).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        it = self.get_object()
        if it.statut not in ("signalee", "en_cours"):
            raise ValidationError({"detail": "Intervention déjà clôturée."})
        it.statut = "annulee"
        it.resolution = str(request.data.get("motif") or "Annulée")
        it.save()
        self._restaurer(it)
        return Response(self.get_serializer(it).data)

    @staticmethod
    def _depense(it, user):
        try:
            from tresorerie.models import Operation
            from tresorerie.services import annee_pour, categorie, creer_operation
            return creer_operation(
                type=Operation.DEPENSE, date=timezone.localdate(), montant=it.cout, categorie=categorie("ENT"),
                libelle=f"Maintenance {it.exemplaire.article.nom} ({it.exemplaire.reference}) — {it.reference}"[:255],
                tiers=it.technicien[:200], statut=Operation.EN_ATTENTE, source="manuel", cree_par=user,
                annee_academique_id=annee_pour(timezone.localdate()), notes=it.resolution[:500],
            )
        except Exception:  # noqa: BLE001  — la trésorerie n'est pas indispensable
            import logging
            logging.getLogger(__name__).exception("Dépense de maintenance non créée")
            return None


# ---------------------------------------------------------------------------
# Inventaire physique
# ---------------------------------------------------------------------------
def _perimetre(c):
    """Emplacements couverts par la campagne."""
    empl = Emplacement.objects.all()
    if c.emplacements.exists():
        return empl.filter(id__in=c.emplacements.values("id"))
    if c.sites.exists():
        return empl.filter(site__in=c.sites.all())
    return empl


def bilan_campagne(c):
    perim = _perimetre(c)
    ids = set(perim.values_list("id", flat=True))
    tout = not c.emplacements.exists() and not c.sites.exists()
    attendus = Exemplaire.objects.filter(statut__in=ACTIFS + ["perdu"]).select_related("article", "emplacement")
    attendus = attendus if tout else attendus.filter(emplacement_id__in=ids)
    constats = {k.exemplaire_id: k for k in c.constats.select_related("exemplaire__article", "exemplaire__emplacement", "emplacement")}
    ligne = lambda e, k=None: {  # noqa: E731
        "exemplaire": e.id, "reference": e.reference, "article": e.article.nom, "statut": e.statut,
        "emplacement_prevu": e.emplacement.chemin if e.emplacement_id else (e.localisation or ""), "emplacement_prevu_id": e.emplacement_id,
        "emplacement_constate": k.emplacement.chemin if k and k.emplacement_id else "", "emplacement_constate_id": k.emplacement_id if k else None,
        "condition": k.condition if k else "", "note": k.note if k else "",
    }
    trouves, deplaces, manquants = [], [], []
    for e in attendus:
        k = constats.get(e.id)
        if not k:
            manquants.append(ligne(e))
        elif k.emplacement_id and k.emplacement_id != e.emplacement_id:
            deplaces.append(ligne(e, k))
        else:
            trouves.append(ligne(e, k))
    ids_att = {e.id for e in attendus}
    hors = [ligne(k.exemplaire, k) for eid, k in constats.items() if eid not in ids_att]  # vus ici mais attendus ailleurs
    par_empl = []
    for em in perim.select_related("site", "batiment"):
        prev = sum(1 for e in attendus if e.emplacement_id == em.id)
        vus = sum(1 for k in constats.values() if k.emplacement_id == em.id)
        if prev or vus:
            par_empl.append({"id": em.id, "chemin": em.chemin, "attendus": prev, "constates": vus})
    total = len(attendus)
    return {
        "attendus": total, "constates": len(constats), "trouves": len(trouves), "deplaces": len(deplaces), "manquants": len(manquants),
        "hors_perimetre": len(hors), "avancement": round((total - len(manquants)) * 100 / total, 1) if total else 100.0,
        "liste_manquants": manquants, "liste_deplaces": deplaces + hors, "liste_trouves": trouves,
        "par_emplacement": sorted(par_empl, key=lambda x: x["chemin"]),
    }


class CampagneViewSet(viewsets.ModelViewSet):
    serializer_class = CampagneSerializer
    permission_classes = [DroitLogistique]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.action in ("constater",):
            return []  # tout personnel / formateur mandaté peut scanner ; contrôlé dans l'action
        return super().get_permissions()

    def get_queryset(self):
        return CampagneInventaire.objects.prefetch_related("sites", "emplacements").select_related("cree_par")

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def destroy(self, request, *args, **kwargs):
        c = self.get_object()
        if c.statut == "cloturee":
            raise ValidationError({"detail": "Une campagne clôturée ne se supprime pas."})
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def bilan(self, request, pk=None):
        c = self.get_object()
        if c.statut == "cloturee" and c.resultat:
            return Response(c.resultat)
        return Response(bilan_campagne(c))

    @action(detail=True, methods=["get"])
    def constats(self, request, pk=None):
        c = self.get_object()
        return Response(ConstatSerializer(c.constats.select_related("exemplaire__article", "emplacement", "scanne_par")[:500], many=True).data)

    @action(detail=True, methods=["post"])
    def constater(self, request, pk=None):
        """{code | exemplaire, emplacement, condition, note} : « ce matériel est ici »."""
        if not peut_signaler(request.user):
            return Response({"detail": "Accès réservé au personnel."}, status=403)
        c = self.get_object()
        if c.statut != "en_cours":
            raise ValidationError({"detail": "Cette campagne est clôturée."})
        code = str(request.data.get("code") or "").strip()
        ex = None
        if request.data.get("exemplaire"):
            ex = Exemplaire.objects.filter(pk=request.data["exemplaire"]).first()
        elif code:
            ex = Exemplaire.objects.filter(Q(code_qr=code) | Q(reference__iexact=code) | Q(numero_serie__iexact=code)).first()
        if not ex:
            raise ValidationError({"detail": f"Aucun matériel ne correspond à « {code} »."})
        empl = _emplacement(request.data.get("emplacement")) or ex.emplacement
        k, cree = Constat.objects.update_or_create(campagne=c, exemplaire=ex, defaults={
            "emplacement": empl, "condition": request.data.get("condition") or "", "note": str(request.data.get("note") or "")[:255],
            "scanne_par": request.user,
        })
        alerte = ""
        if empl and ex.emplacement_id and empl.id != ex.emplacement_id:
            alerte = f"Attendu à : {ex.emplacement.chemin}"
        elif not ex.emplacement_id:
            alerte = "Ce matériel n'avait pas d'emplacement enregistré."
        if ex.statut in ("reforme",):
            alerte = "Attention : ce matériel est enregistré comme réformé."
        return Response({"constat": ConstatSerializer(k).data, "nouveau": cree, "alerte": alerte,
                         "exemplaire": {"reference": ex.reference, "article": ex.article.nom}})

    @action(detail=True, methods=["delete"], url_path=r"constats/(?P<constat_id>\d+)")
    def supprimer_constat(self, request, pk=None, constat_id=None):
        c = self.get_object()
        if c.statut != "en_cours":
            raise ValidationError({"detail": "Cette campagne est clôturée."})
        c.constats.filter(pk=constat_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        """appliquer_deplacements : met à jour l'emplacement du matériel trouvé ailleurs ;
        marquer_perdus : passe le matériel non trouvé au statut « Perdu / introuvable »."""
        c = self.get_object()
        if c.statut != "en_cours":
            raise ValidationError({"detail": "Campagne déjà clôturée."})
        oui = lambda k: str(request.data.get(k)).lower() in ("1", "true", "oui")  # noqa: E731
        with transaction.atomic():
            b = bilan_campagne(c)
            if oui("appliquer_deplacements"):
                for l in b["liste_deplaces"]:
                    if l["emplacement_constate_id"]:
                        ex = Exemplaire.objects.get(pk=l["exemplaire"])
                        source = ex.emplacement
                        ex.emplacement_id = l["emplacement_constate_id"]
                        ex.save()
                        _mvt(ex, "inventaire", request.user, f"Inventaire {c.reference} : trouvé ici", source=source, destination=ex.emplacement)
            for k in c.constats.exclude(condition="").select_related("exemplaire"):
                if k.exemplaire.condition != k.condition:
                    Exemplaire.objects.filter(pk=k.exemplaire_id).update(condition=k.condition)
            # Matériel retrouvé alors qu'il était « perdu »
            for k in c.constats.filter(exemplaire__statut="perdu").select_related("exemplaire"):
                ex = k.exemplaire
                ex.statut = "en_utilisation" if ex.attributaire_object_id else "en_stock"
                ex.save(update_fields=["statut"])
                _mvt(ex, "inventaire", request.user, f"Inventaire {c.reference} : retrouvé")
            if oui("marquer_perdus"):
                for l in b["liste_manquants"]:
                    ex = Exemplaire.objects.get(pk=l["exemplaire"])
                    if ex.statut != "perdu":
                        ex.statut = "perdu"
                        ex.save(update_fields=["statut"])
                        _mvt(ex, "inventaire", request.user, f"Inventaire {c.reference} : introuvable")
            c.statut, c.date_cloture = "cloturee", timezone.now()
            c.commentaire = str(request.data.get("commentaire") or c.commentaire)
            c.resultat = {**b, "deplacements_appliques": oui("appliquer_deplacements"), "perdus_marques": oui("marquer_perdus")}
            c.save()
        return Response(CampagneSerializer(c).data)


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------
class InventaireStatsView(APIView):
    permission_classes = [LectureLogistique]

    def get(self, request):
        today = timezone.localdate()
        ex = Exemplaire.objects.select_related("article")
        actifs = [e for e in ex.filter(statut__in=ACTIFS)]
        par_statut = {k: 0 for k, _ in Exemplaire.STATUTS}
        for r in Exemplaire.objects.values("statut").annotate(n=Count("id")):
            par_statut[r["statut"]] = r["n"]
        valeur_achat = sum(e.valeur_origine for e in actifs)
        valeur_nette = sum(e.valeur_actuelle(today) for e in actifs)
        par_categorie = {}
        for e in actifs:
            c = par_categorie.setdefault(e.article.categorie, {"categorie": e.article.categorie, "nombre": 0, "valeur_achat": 0.0, "valeur_nette": 0.0})
            c["nombre"] += 1
            c["valeur_achat"] += float(e.valeur_origine)
            c["valeur_nette"] += float(e.valeur_actuelle(today))
        par_site = list(Site.objects.filter(actif=True).annotate(
            nombre=Count("emplacements__exemplaires", filter=Q(emplacements__exemplaires__statut__in=ACTIFS))).values("id", "nom", "nombre"))
        non_localises = Exemplaire.objects.filter(statut__in=ACTIFS, emplacement__isnull=True).count()
        if non_localises:
            par_site.append({"id": None, "nom": "Sans emplacement", "nombre": non_localises})
        ouvertes = Intervention.objects.filter(statut__in=["signalee", "en_cours"])
        cout_annee = Intervention.objects.filter(date_fin__year=today.year).aggregate(t=Sum("cout"))["t"] or 0
        consommables_bas = list(Article.objects.filter(type_article="consommable", stock__lte=F("seuil_alerte")).values(
            "id", "nom", "stock", "seuil_alerte", "unite")[:15])
        equipements_bas = Article.objects.filter(type_article="equipement").annotate(
            nb=Count("exemplaires", filter=Q(exemplaires__statut="en_stock"))).filter(nb__lte=F("seuil_alerte"), seuil_alerte__gt=0).count()
        garanties = ExemplaireSerializer(ex.filter(statut__in=ACTIFS, date_fin_garantie__gte=today,
                                                   date_fin_garantie__lte=today + timedelta(days=60)).order_by("date_fin_garantie")[:10], many=True).data
        amortis = sum(1 for e in actifs if e.valeur_origine > 0 and e.valeur_actuelle(today) == 0)
        campagne = CampagneInventaire.objects.filter(statut="en_cours").first()
        return Response({
            "total_articles": Article.objects.count(),
            "total_exemplaires": len(actifs),
            "par_statut": par_statut,
            # compatibilité avec l'ancien écran
            "en_stock": par_statut.get("en_stock", 0), "en_utilisation": par_statut.get("en_utilisation", 0),
            "en_panne": par_statut.get("en_panne", 0), "en_maintenance": par_statut.get("en_maintenance", 0),
            "reformes": par_statut.get("reforme", 0), "valeur_stock": float(valeur_achat),
            "valeur_achat": float(valeur_achat), "valeur_nette": float(valeur_nette), "amortis": amortis,
            "par_categorie": sorted(par_categorie.values(), key=lambda x: -x["nombre"]),
            "par_site": par_site,
            "nb_sites": Site.objects.filter(actif=True).count(), "nb_emplacements": Emplacement.objects.filter(actif=True).count(),
            "non_localises": non_localises,
            "pannes_ouvertes": ouvertes.count(), "pannes_urgentes": ouvertes.filter(priorite__in=["haute", "urgente"]).count(),
            "dernieres_pannes": InterventionSerializer(ouvertes.select_related("exemplaire__article", "signale_par")[:6], many=True).data,
            "cout_maintenance_annee": float(cout_annee),
            "consommables_bas": consommables_bas, "articles_stock_bas": equipements_bas + len(consommables_bas),
            "garanties_bientot": garanties,
            "campagne_en_cours": CampagneSerializer(campagne).data if campagne else None,
            "derniers_mouvements": MouvementSerializer(Mouvement.objects.select_related("exemplaire__article", "utilisateur")[:10], many=True).data,
            "mouvements_30j": Mouvement.objects.filter(date__gte=timezone.now() - timedelta(days=30)).count(),
        })


# Legacy viewset kept for existing demandes system
class InventaireViewSet(viewsets.ModelViewSet):
    queryset = Inventaire.objects.all()
    serializer_class = InventaireSerializer
    permission_classes = [DroitLogistique]
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

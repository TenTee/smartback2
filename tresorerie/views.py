import datetime as dt
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Budget, CategorieFinance, ClotureCaisse, CompteTresorerie, Fournisseur, LigneBudget, Operation, Rapprochement,
)
from .serializers import (
    CategorieSerializer, ClotureSerializer, CompteSerializer, FournisseurSerializer, OperationSerializer,
    RapprochementSerializer,
)
from .services import (
    OperationVerrouillee, annee_pour, categorie, creer_operation, derniere_cloture, initialiser, periode_annee, recouvrement,
    verifier_verrou,
)

ZERO = Decimal("0")


def _droit(user):
    from notifications.services import droit, profil
    if profil(user) != "personnel":
        return "none"
    return droit(user, "finance")


class DroitFinance(BasePermission):
    """Lecture : droit Finances ≥ lecture. Écriture : droit Finances = écriture."""
    message = "Votre rôle ne donne pas accès aux finances (ou seulement en lecture)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        d = _droit(request.user)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return d != "none"
        return d == "ecriture"


class Pagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 10000


def _date(v):
    from django.utils.dateparse import parse_date
    try:
        return parse_date(v) if v else None
    except (TypeError, ValueError):
        return None


def _annee(request):
    from academique.middleware import get_current_academic_year_id
    from academique.models import AnneeAcademique
    aid = request.query_params.get("annee") or get_current_academic_year_id()
    a = AnneeAcademique.objects.filter(pk=aid).first() if aid else None
    return a or AnneeAcademique.objects.filter(est_active=True).first()


def _periode(request):
    dd, df = _date(request.query_params.get("date_debut")), _date(request.query_params.get("date_fin"))
    if dd and df:
        return dd, df
    return periode_annee(_annee(request))


# ---------------------------------------------------------------------------
class CompteViewSet(viewsets.ModelViewSet):
    serializer_class = CompteSerializer
    permission_classes = [DroitFinance]
    pagination_class = None

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "annee": _annee(self.request)}

    def get_queryset(self):
        initialiser()
        qs = CompteTresorerie.objects.all()
        if self.request.query_params.get("actifs") in ("1", "true"):
            qs = qs.filter(actif=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        c = self.get_object()
        if Operation.objects.filter(Q(compte=c) | Q(compte_destination=c)).exists():
            c.actif = False
            c.save(update_fields=["actif"])
            return Response({"detail": "Ce compte a des opérations : il a été désactivé."})
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def releve(self, request, pk=None):
        """Relevé du compte pour l'année académique choisie : solde d'ouverture, mouvements (dont reports entre années)
        avec solde progressif, solde de clôture."""
        c = self.get_object()
        annee = _annee(request)
        dd, df = _periode(request)
        ouverture = c.solde_annee(annee, dd - dt.timedelta(days=1))
        fin_annee = getattr(annee, "date_fin", None)
        cedes_tardifs = Q(type=Operation.REPORT, annee_origine=annee, date__gt=df) if (fin_annee and df >= fin_annee) else Q(pk__in=[])
        ops = (Operation.objects.filter(statut=Operation.VALIDEE)
               .filter(Q(date__gte=dd, date__lte=df, annee_academique=annee)
                       | Q(date__gte=dd, date__lte=df, type=Operation.REPORT, annee_origine=annee) | cedes_tardifs)
               .filter(Q(compte=c) | Q(compte_destination=c, type=Operation.VIREMENT))
               .select_related("categorie", "compte", "compte_destination", "annee_origine", "annee_academique").order_by("date", "id"))
        solde, lignes, entrees, sorties = ouverture, [], ZERO, ZERO
        for o in ops:
            if o.type == Operation.REPORT:
                entree = o.montant if o.annee_academique_id == getattr(annee, "id", None) else ZERO
                libelle_cat = (f"Report de {o.annee_origine.libelle}" if entree else f"Report vers {o.annee_academique.libelle}") if o.annee_origine_id else "Report"
            else:
                entree = o.montant if (o.type == Operation.RECETTE or (o.type == Operation.VIREMENT and o.compte_destination_id == c.id)) else ZERO
                libelle_cat = o.categorie.libelle if o.categorie_id else ("Virement interne" if o.type == Operation.VIREMENT else "")
            sortie = o.montant if entree == ZERO else ZERO
            solde += entree - sortie
            entrees += entree
            sorties += sortie
            lignes.append({
                "id": o.id, "numero": o.numero, "date": o.date, "libelle": o.libelle, "tiers": o.tiers, "categorie": libelle_cat,
                "mode": o.get_mode_display(), "reference": o.reference, "entree": float(entree), "sortie": float(sortie),
                "solde": float(solde), "rapproche": bool(o.rapprochement_id),
            })
        return Response({
            "compte": CompteSerializer(c, context={"annee": annee}).data, "date_debut": dd, "date_fin": df,
            "annee": annee.libelle if annee else None,
            "solde_ouverture": float(ouverture), "total_entrees": float(entrees), "total_sorties": float(sorties),
            "solde_cloture": float(solde), "lignes": lignes,
        })


class CategorieViewSet(viewsets.ModelViewSet):
    serializer_class = CategorieSerializer
    permission_classes = [DroitFinance]
    pagination_class = None

    def get_queryset(self):
        initialiser()
        qs = CategorieFinance.objects.all()
        if self.request.query_params.get("sens"):
            qs = qs.filter(sens=self.request.query_params["sens"])
        if self.request.query_params.get("actives") in ("1", "true"):
            qs = qs.filter(actif=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        c = self.get_object()
        if c.systeme:
            raise ValidationError({"detail": "Catégorie utilisée par les opérations automatiques : elle ne peut pas être supprimée."})
        if c.operations.exists() or c.lignes_budget.exists():
            c.actif = False
            c.save(update_fields=["actif"])
            return Response({"detail": "Catégorie utilisée : elle a été désactivée."})
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FournisseurViewSet(viewsets.ModelViewSet):
    serializer_class = FournisseurSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "annee": _annee(self.request)}

    permission_classes = [DroitFinance]
    pagination_class = None

    def get_queryset(self):
        qs = Fournisseur.objects.all()
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(contact__icontains=q) | Q(telephone__icontains=q) | Q(niu__icontains=q))
        return qs

    def destroy(self, request, *args, **kwargs):
        f = self.get_object()
        if f.operations.exists():
            f.actif = False
            f.save(update_fields=["actif"])
            return Response({"detail": "Fournisseur lié à des opérations : il a été désactivé."})
        f.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
CHAMPS_LIBRES = {"libelle", "tiers", "fournisseur", "reference", "notes", "piece_jointe", "etudiant", "date_echeance"}


class OperationViewSet(viewsets.ModelViewSet):
    """Journal de trésorerie.

    Recettes et virements : validés à la saisie. Dépenses : à approuver → approuvée → payée (validée),
    ou directement payée (« deja_payee »). Une opération validée ne se supprime pas : elle s'annule.
    """

    serializer_class = OperationSerializer
    permission_classes = [DroitFinance]
    pagination_class = Pagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Operation.objects.select_related(
            "compte", "compte_destination", "categorie", "fournisseur", "etudiant", "cree_par", "approuve_par", "valide_par",
        )
        p = self.request.query_params
        if self.action in ("list", "resume") and p.get("toutes_annees") not in ("1", "true"):
            # Chaque année académique a sa propre gestion : on ne voit que les opérations de l'année choisie.
            annee = _annee(self.request)
            if annee:
                qs = qs.filter(Q(annee_academique=annee) | Q(type=Operation.REPORT, annee_origine=annee))
        if p.get("type"):
            qs = qs.filter(type__in=p["type"].split(","))
        if p.get("statut"):
            qs = qs.filter(statut__in=p["statut"].split(","))
        if p.get("compte"):
            qs = qs.filter(Q(compte_id=p["compte"]) | Q(compte_destination_id=p["compte"]))
        if p.get("categorie"):
            qs = qs.filter(categorie_id=p["categorie"])
        if p.get("source"):
            qs = qs.filter(source__in=p["source"].split(","))
        for champ in ("fournisseur", "etudiant", "annee_academique"):
            if p.get(champ):
                qs = qs.filter(**{f"{champ}_id": p[champ]})
        if p.get("date_debut"):
            qs = qs.filter(date__gte=_date(p["date_debut"]))
        if p.get("date_fin"):
            qs = qs.filter(date__lte=_date(p["date_fin"]))
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(numero__icontains=q) | Q(libelle__icontains=q) | Q(tiers__icontains=q) | Q(reference__icontains=q)
                           | Q(etudiant__nom__icontains=q) | Q(fournisseur__nom__icontains=q))
        if p.get("non_rapprochees") in ("1", "true"):
            qs = qs.filter(rapprochement__isnull=True, statut=Operation.VALIDEE)
        return qs

    @staticmethod
    def _bool(v):
        return str(v).lower() in ("1", "true", "oui", "on")

    def perform_create(self, serializer):
        d = serializer.validated_data
        type_ = d["type"]
        user = self.request.user
        maintenant = timezone.now()
        extra = {"cree_par": user, "source": "manuel"}
        if type_ == Operation.REPORT:
            raise ValidationError({"type": ["Utilisez « Reprendre l'argent d'une autre année » dans Trésorerie."]})
        if not d.get("annee_academique"):
            extra["annee_academique_id"] = annee_pour(d["date"])
        if type_ == Operation.DEPENSE and not self._bool(self.request.data.get("deja_payee")):
            extra.update(statut=Operation.EN_ATTENTE)
        else:
            if type_ == Operation.DEPENSE and not d.get("compte"):
                raise ValidationError({"compte": ["Choisissez la caisse ou le compte qui a payé."]})
            extra.update(statut=Operation.VALIDEE, valide_par=user, valide_le=maintenant)
            if type_ == Operation.DEPENSE:
                extra.update(approuve_par=user, approuve_le=maintenant)
        try:
            if extra["statut"] == Operation.VALIDEE:
                verifier_verrou(d["date"], d.get("compte"), d.get("compte_destination"))
        except OperationVerrouillee as e:
            raise ValidationError({"date": [str(e)]})
        op = creer_operation(**d, **extra)
        serializer.instance = op
        if op.statut == Operation.EN_ATTENTE:
            self._notifier_a_approuver(op)

    def _notifier_a_approuver(self, op):
        try:
            from notifications.services import notifier
            notifier(["finance"], "depense_a_approuver", f"Dépense à approuver : {op.montant:,.0f} FCFA".replace(",", " "),
                     f"{op.numero} — {op.libelle}", lien="/finances/operations?onglet=a_approuver", niveau="alerte")
        except Exception:  # noqa: BLE001
            pass

    def perform_update(self, serializer):
        op = serializer.instance
        if op.source != "manuel":
            raise ValidationError({"detail": "Opération créée automatiquement (scolarité, paie) : modifiez-la depuis son module."})
        if op.statut == Operation.ANNULEE or op.rapprochement_id:
            raise ValidationError({"detail": "Opération annulée ou rapprochée : elle ne peut plus être modifiée."})
        d = serializer.validated_data
        if op.statut == Operation.VALIDEE:
            interdits = [k for k in d if k not in CHAMPS_LIBRES and getattr(op, k) != d[k]]
            if interdits:
                raise ValidationError({"detail": "Opération validée : le montant, la date, le compte et la catégorie ne se modifient plus. Annulez-la puis ressaisissez-la."})
        try:
            verifier_verrou(op.date, op.compte, op.compte_destination) if op.statut == Operation.VALIDEE else None
        except OperationVerrouillee as e:
            raise ValidationError({"detail": str(e)})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        op = self.get_object()
        if op.statut in (Operation.EN_ATTENTE, Operation.REJETEE) and op.source == "manuel":
            op.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        raise ValidationError({"detail": "Une opération validée ou approuvée ne se supprime pas : utilisez « Annuler »."})

    # ---- circuit de validation
    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        op = self.get_object()
        if op.type != Operation.DEPENSE or op.statut != Operation.EN_ATTENTE:
            raise ValidationError({"detail": "Seule une dépense en attente peut être approuvée."})
        op.statut, op.approuve_par, op.approuve_le = Operation.APPROUVEE, request.user, timezone.now()
        op.save(update_fields=["statut", "approuve_par", "approuve_le"])
        return Response(OperationSerializer(op, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        op = self.get_object()
        if op.statut not in (Operation.EN_ATTENTE, Operation.APPROUVEE):
            raise ValidationError({"detail": "Seule une dépense non payée peut être rejetée."})
        op.statut, op.motif_rejet = Operation.REJETEE, str(request.data.get("motif") or "")[:255]
        op.approuve_par, op.approuve_le = request.user, timezone.now()
        op.save(update_fields=["statut", "motif_rejet", "approuve_par", "approuve_le"])
        return Response(OperationSerializer(op, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def payer(self, request, pk=None):
        """Dépense : paiement. Recette en attente : validation de l'encaissement (l'argent est arrivé)."""
        op = self.get_object()
        if not ((op.type == Operation.DEPENSE and op.statut in (Operation.EN_ATTENTE, Operation.APPROUVEE))
                or (op.type == Operation.RECETTE and op.statut == Operation.EN_ATTENTE)):
            raise ValidationError({"detail": "Seule une dépense à payer ou une recette à valider peut être réglée."})
        compte = get_object_or_404(CompteTresorerie, pk=request.data.get("compte") or op.compte_id or 0)
        date = _date(request.data.get("date")) or timezone.localdate()
        try:
            verifier_verrou(date, compte)
        except OperationVerrouillee as e:
            raise ValidationError({"detail": str(e)})
        maintenant = timezone.now()
        op.compte, op.date = compte, date
        op.mode = request.data.get("mode") or op.mode
        if request.data.get("reference"):
            op.reference = str(request.data["reference"])[:100]
        if op.statut == Operation.EN_ATTENTE:
            op.approuve_par, op.approuve_le = request.user, maintenant
        op.statut, op.valide_par, op.valide_le = Operation.VALIDEE, request.user, maintenant
        op.save()
        return Response(OperationSerializer(op, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        op = self.get_object()
        if op.source != "manuel" and op.source_type != "revenu":
            raise ValidationError({"detail": "Opération automatique : annulez-la depuis son module (paiement de scolarité, paie)."})
        if op.statut == Operation.ANNULEE:
            raise ValidationError({"detail": "Opération déjà annulée."})
        if op.rapprochement_id:
            raise ValidationError({"detail": "Opération rapprochée avec un relevé bancaire : elle ne peut plus être annulée."})
        if op.statut == Operation.VALIDEE and op.type != Operation.REPORT:
            try:
                verifier_verrou(op.date, op.compte, op.compte_destination)
            except OperationVerrouillee as e:
                raise ValidationError({"detail": str(e)})
        if op.type == Operation.REPORT and op.statut == Operation.VALIDEE and op.compte:
            reste = op.compte.solde_annee(op.annee_academique) - op.montant
            if reste < 0:
                raise ValidationError({"detail": f"Impossible : l'année {op.annee_academique} a déjà dépensé cet argent (solde après annulation : {reste:,.0f} FCFA).".replace(",", " ")})
        op.statut, op.motif_rejet = Operation.ANNULEE, str(request.data.get("motif") or "Annulée")[:255]
        op.save(update_fields=["statut", "motif_rejet"])
        return Response(OperationSerializer(op, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def resume(self, request):
        """Totaux de la liste filtrée (recettes, dépenses, virements validés)."""
        qs = self.filter_queryset(self.get_queryset())
        val = qs.filter(statut=Operation.VALIDEE)
        r = val.filter(type=Operation.RECETTE).aggregate(t=Sum("montant"))["t"] or ZERO
        d = val.filter(type=Operation.DEPENSE).aggregate(t=Sum("montant"))["t"] or ZERO
        return Response({
            "recettes": float(r), "depenses": float(d), "solde": float(r - d), "nombre": qs.count(),
            "a_approuver": qs.filter(statut=Operation.EN_ATTENTE).count(),
            "a_payer": qs.filter(statut=Operation.APPROUVEE).count(),
        })


# ---------------------------------------------------------------------------
class ClotureViewSet(viewsets.ModelViewSet):
    serializer_class = ClotureSerializer
    permission_classes = [DroitFinance]
    pagination_class = Pagination
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = ClotureCaisse.objects.select_related("compte", "cree_par")
        if self.request.query_params.get("compte"):
            qs = qs.filter(compte_id=self.request.query_params["compte"])
        return qs

    def create(self, request, *args, **kwargs):
        compte = get_object_or_404(CompteTresorerie, pk=request.data.get("compte"))
        date = _date(request.data.get("date")) or timezone.localdate()
        if date > timezone.localdate():
            raise ValidationError({"date": ["On ne clôture pas une date future."]})
        derniere = derniere_cloture(compte.id)
        if derniere and date <= derniere:
            raise ValidationError({"date": [f"Ce compte est déjà clôturé jusqu'au {derniere:%d/%m/%Y}."]})
        try:
            reel = Decimal(str(request.data.get("solde_reel")))
        except Exception:  # noqa: BLE001
            raise ValidationError({"solde_reel": ["Indiquez le solde réellement compté."]})
        with transaction.atomic():
            theorique = compte.solde(date)
            ecart = reel - theorique
            op_ecart = None
            if ecart and str(request.data.get("regulariser", "")).lower() in ("1", "true", "oui"):
                op_ecart = creer_operation(
                    type=Operation.RECETTE if ecart > 0 else Operation.DEPENSE, date=date, montant=abs(ecart), compte=compte,
                    categorie=categorie("REC-AUT" if ecart > 0 else "DEP-AUT"),
                    libelle=f"{'Excédent' if ecart > 0 else 'Manquant'} de caisse constaté à la clôture du {date:%d/%m/%Y}",
                    statut=Operation.VALIDEE, mode="especes", cree_par=request.user, valide_par=request.user,
                    valide_le=timezone.now(), approuve_par=request.user, approuve_le=timezone.now(),
                )
            c = ClotureCaisse.objects.create(
                compte=compte, date=date, solde_theorique=theorique, solde_reel=reel, ecart=ecart,
                billetage=request.data.get("billetage") or {}, commentaire=str(request.data.get("commentaire") or ""),
                operation_ecart=op_ecart, cree_par=request.user,
            )
        return Response(ClotureSerializer(c).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        c = self.get_object()
        if ClotureCaisse.objects.filter(compte=c.compte, date__gt=c.date).exists():
            raise ValidationError({"detail": "Seule la dernière clôture d'un compte peut être rouverte."})
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def apercu(self, request):
        """Solde théorique d'un compte à une date (avant clôture) et opérations du jour."""
        compte = get_object_or_404(CompteTresorerie, pk=request.query_params.get("compte"))
        date = _date(request.query_params.get("date")) or timezone.localdate()
        jour = Operation.objects.filter(statut=Operation.VALIDEE, date=date).filter(Q(compte=compte) | Q(compte_destination=compte))
        entrees = jour.filter(Q(type=Operation.RECETTE) | Q(type=Operation.VIREMENT, compte_destination=compte)).aggregate(t=Sum("montant"))["t"] or ZERO
        sorties = jour.filter(Q(type=Operation.DEPENSE) | Q(type=Operation.VIREMENT, compte=compte)).aggregate(t=Sum("montant"))["t"] or ZERO
        return Response({
            "compte": compte.id, "date": date, "solde_theorique": float(compte.solde(date)),
            "solde_veille": float(compte.solde(date - dt.timedelta(days=1))), "entrees_du_jour": float(entrees),
            "sorties_du_jour": float(sorties), "nb_operations": jour.count(), "derniere_cloture": derniere_cloture(compte.id),
        })


class RapprochementViewSet(viewsets.ModelViewSet):
    serializer_class = RapprochementSerializer
    permission_classes = [DroitFinance]
    pagination_class = Pagination
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = Rapprochement.objects.select_related("compte", "cree_par")
        if self.request.query_params.get("compte"):
            qs = qs.filter(compte_id=self.request.query_params["compte"])
        return qs

    def create(self, request, *args, **kwargs):
        compte = get_object_or_404(CompteTresorerie, pk=request.data.get("compte"))
        date = _date(request.data.get("date_releve")) or timezone.localdate()
        try:
            solde_releve = Decimal(str(request.data.get("solde_releve")))
        except Exception:  # noqa: BLE001
            raise ValidationError({"solde_releve": ["Indiquez le solde du relevé bancaire."]})
        ids = [int(i) for i in request.data.get("operations") or []]
        with transaction.atomic():
            r = Rapprochement.objects.create(compte=compte, date_releve=date, solde_releve=solde_releve,
                                             commentaire=str(request.data.get("commentaire") or ""), cree_par=request.user)
            Operation.objects.filter(pk__in=ids, statut=Operation.VALIDEE, rapprochement__isnull=True, date__lte=date).filter(
                Q(compte=compte) | Q(compte_destination=compte)).update(rapprochement=r)
            pointees = Operation.objects.filter(rapprochement__compte=compte, statut=Operation.VALIDEE)
            e = pointees.filter(Q(type=Operation.RECETTE, compte=compte) | Q(type=Operation.VIREMENT, compte_destination=compte)).aggregate(t=Sum("montant"))["t"] or ZERO
            s = pointees.filter(Q(type=Operation.DEPENSE, compte=compte) | Q(type=Operation.VIREMENT, compte=compte)).aggregate(t=Sum("montant"))["t"] or ZERO
            r.solde_pointe = Decimal(compte.solde_initial) + e - s
            r.ecart = solde_releve - r.solde_pointe
            r.save(update_fields=["solde_pointe", "ecart"])
        return Response(RapprochementSerializer(r).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        r = self.get_object()
        if Rapprochement.objects.filter(compte=r.compte, cree_le__gt=r.cree_le).exists():
            raise ValidationError({"detail": "Seul le dernier rapprochement d'un compte peut être annulé."})
        Operation.objects.filter(rapprochement=r).update(rapprochement=None)
        r.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
class BudgetView(APIView):
    """GET ?annee= : prévu / réalisé par catégorie. PUT {annee, lignes: [{categorie, montant_prevu, notes}], commentaire}."""
    permission_classes = [DroitFinance]

    def _reponse(self, annee):
        initialiser()
        budget = Budget.objects.filter(annee_academique=annee).first()
        prevu = {l.categorie_id: l for l in budget.lignes.all()} if budget else {}
        dd, df = periode_annee(annee)
        realise = dict(Operation.objects.filter(statut=Operation.VALIDEE, annee_academique=annee)
                       .exclude(categorie__isnull=True).values("categorie").annotate(t=Sum("montant")).values_list("categorie", "t"))
        engage = dict(Operation.objects.filter(statut__in=[Operation.EN_ATTENTE, Operation.APPROUVEE], annee_academique=annee)
                      .exclude(categorie__isnull=True).values("categorie").annotate(t=Sum("montant")).values_list("categorie", "t"))
        lignes = []
        for c in CategorieFinance.objects.filter(Q(actif=True) | Q(pk__in=list(prevu))):
            p = prevu.get(c.id)
            mp = float(p.montant_prevu) if p else 0.0
            r = float(realise.get(c.id) or 0)
            lignes.append({
                "categorie": c.id, "code": c.code, "libelle": c.libelle, "sens": c.sens, "prevu": mp, "realise": r,
                "engage": float(engage.get(c.id) or 0), "ecart": r - mp, "taux": round(r * 100 / mp, 1) if mp else None,
                "notes": p.notes if p else "",
            })
        tot = lambda sens, k: sum(l[k] for l in lignes if l["sens"] == sens)  # noqa: E731
        return {
            "annee": {"id": annee.id, "libelle": annee.libelle, "date_debut": dd, "date_fin": df} if annee else None,
            "commentaire": budget.commentaire if budget else "", "existe": bool(budget), "lignes": lignes,
            "totaux": {s: {"prevu": tot(s, "prevu"), "realise": tot(s, "realise"), "engage": tot(s, "engage")} for s in ("recette", "depense")},
        }

    def get(self, request):
        annee = _annee(request)
        if not annee:
            return Response({"detail": "Aucune année académique."}, status=400)
        return Response(self._reponse(annee))

    def put(self, request):
        from academique.models import AnneeAcademique
        annee = get_object_or_404(AnneeAcademique, pk=request.data.get("annee"))
        with transaction.atomic():
            budget, _ = Budget.objects.get_or_create(annee_academique=annee)
            if "commentaire" in request.data:
                budget.commentaire = str(request.data.get("commentaire") or "")
                budget.save()
            for l in request.data.get("lignes") or []:
                try:
                    montant = Decimal(str(l.get("montant_prevu") or 0))
                except Exception:  # noqa: BLE001
                    continue
                if montant < 0:
                    raise ValidationError({"detail": "Un montant prévu ne peut pas être négatif."})
                LigneBudget.objects.update_or_create(budget=budget, categorie_id=l.get("categorie"),
                                                     defaults={"montant_prevu": montant, "notes": str(l.get("notes") or "")[:255]})
        return Response(self._reponse(annee))


# ---------------------------------------------------------------------------
def _par_mois(qs, dd, df):
    rows = qs.annotate(m=TruncMonth("date")).values("m", "type").annotate(t=Sum("montant"))
    mois = []
    d = dt.date(dd.year, dd.month, 1)
    while d <= df:
        mois.append(d)
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    data = {m: {"mois": m.strftime("%Y-%m"), "recettes": 0.0, "depenses": 0.0} for m in mois}
    for r in rows:
        m = r["m"].date() if hasattr(r["m"], "date") else r["m"]
        if m in data and r["type"] in (Operation.RECETTE, Operation.DEPENSE):
            data[m]["recettes" if r["type"] == Operation.RECETTE else "depenses"] += float(r["t"])
    res = list(data.values())
    for x in res:
        x["solde"] = x["recettes"] - x["depenses"]
    return res


class TableauDeBordView(APIView):
    """Tableau de bord de l'année académique choisie (chaque année a sa propre caisse)."""
    permission_classes = [DroitFinance]

    def get(self, request):
        initialiser()
        annee = _annee(request)
        dd, df = periode_annee(annee)
        today = timezone.localdate()
        debut_mois = today.replace(day=1)
        de_annee = Operation.objects.filter(annee_academique=annee) if annee else Operation.objects.all()
        val = de_annee.filter(statut=Operation.VALIDEE)

        def total(qs, type_):
            return float(qs.filter(type=type_).aggregate(t=Sum("montant"))["t"] or 0)

        comptes = [{"id": c.id, "nom": c.nom, "type": c.type, "solde": float(c.solde_annee(annee)),
                    "solde_physique": float(c.solde()), "derniere_cloture": derniere_cloture(c.id)}
                   for c in CompteTresorerie.objects.filter(actif=True)]
        mois = val.filter(date__gte=debut_mois, date__lte=today)
        par_cat = lambda type_: [  # noqa: E731
            {"categorie": r["categorie__libelle"] or "Sans catégorie", "montant": float(r["t"])}
            for r in val.filter(type=type_).values("categorie__libelle").annotate(t=Sum("montant")).order_by("-t")
        ]
        attente = de_annee.filter(statut=Operation.EN_ATTENTE)
        a_payer = de_annee.filter(statut=Operation.APPROUVEE)
        rec = recouvrement(annee)
        attendu = sum(x["attendu"] for x in rec)
        encaisse = sum(x["encaisse"] for x in rec)
        budget = BudgetView()._reponse(annee) if annee else None
        caisses_non_cloturees = [
            c for c in comptes if c["type"] == CompteTresorerie.CAISSE and (not c["derniere_cloture"] or c["derniere_cloture"] < today - dt.timedelta(days=1))
        ]
        reports_recus = val.filter(type=Operation.REPORT).aggregate(t=Sum("montant"))["t"] or 0
        reports_cedes = Operation.objects.filter(statut=Operation.VALIDEE, type=Operation.REPORT, annee_origine=annee).aggregate(t=Sum("montant"))["t"] or 0 if annee else 0
        fin_graphe = min(df, today) if dd <= today else df
        return Response({
            "periode": {"date_debut": dd, "date_fin": df, "annee": annee.libelle if annee else None, "annee_id": annee.id if annee else None,
                        "en_cours": dd <= today <= df},
            "tresorerie": {"total": sum(c["solde"] for c in comptes), "total_physique": sum(c["solde_physique"] for c in comptes),
                           "comptes": comptes, "reports_recus": float(reports_recus), "reports_cedes": float(reports_cedes)},
            "mois": {"recettes": total(mois, Operation.RECETTE), "depenses": total(mois, Operation.DEPENSE)},
            "periode_totaux": {"recettes": total(val, Operation.RECETTE), "depenses": total(val, Operation.DEPENSE)},
            "evolution": _par_mois(val, dd, fin_graphe),
            "depenses_par_categorie": par_cat(Operation.DEPENSE),
            "recettes_par_categorie": par_cat(Operation.RECETTE),
            "scolarite": {"attendu": attendu, "encaisse": encaisse, "reste": max(0, attendu - encaisse),
                          "taux": round(encaisse * 100 / attendu, 1) if attendu else 0, "classes": rec},
            "a_faire": {
                "a_approuver": {"nombre": attente.filter(type=Operation.DEPENSE).count(),
                                "montant": float(attente.filter(type=Operation.DEPENSE).aggregate(t=Sum("montant"))["t"] or 0)},
                "recettes_a_valider": {"nombre": attente.filter(type=Operation.RECETTE).count(),
                                       "montant": float(attente.filter(type=Operation.RECETTE).aggregate(t=Sum("montant"))["t"] or 0)},
                "a_payer": {"nombre": a_payer.count(), "montant": float(a_payer.aggregate(t=Sum("montant"))["t"] or 0)},
                "en_retard": a_payer.filter(date_echeance__lt=today).count(),
                "caisses_a_cloturer": [c["nom"] for c in caisses_non_cloturees],
                "non_rapprochees": val.filter(compte__type=CompteTresorerie.BANQUE, rapprochement__isnull=True).count(),
            },
            "budget": budget["totaux"] if budget else None,
            "dernieres_operations": OperationSerializer(
                de_annee.select_related("compte", "categorie", "etudiant", "fournisseur").exclude(statut=Operation.ANNULEE)[:10],
                many=True, context={"request": request},
            ).data,
        })


class RapportsView(APIView):
    """GET ?type=synthese|recouvrement&date_debut&date_fin&annee"""
    permission_classes = [DroitFinance]

    def get(self, request):
        type_ = request.query_params.get("type", "synthese")
        if type_ == "recouvrement":
            return Response({"classes": recouvrement(_annee(request))})
        annee = _annee(request)
        dd, df = _periode(request)
        val = Operation.objects.filter(statut=Operation.VALIDEE, date__gte=dd, date__lte=df)
        if annee:
            val = val.filter(annee_academique=annee)
        mois = _par_mois(val, dd, df)
        cle_mois = [m["mois"] for m in mois]
        matrice = defaultdict(lambda: defaultdict(float))
        infos = {}
        for r in val.filter(type__in=[Operation.RECETTE, Operation.DEPENSE]).annotate(m=TruncMonth("date")).values(
                "categorie_id", "categorie__libelle", "categorie__code", "categorie__compte_comptable", "type", "m").annotate(t=Sum("montant")):
            m = (r["m"].date() if hasattr(r["m"], "date") else r["m"]).strftime("%Y-%m")
            matrice[r["categorie_id"]][m] += float(r["t"])
            infos[r["categorie_id"]] = {"categorie": r["categorie__libelle"] or "Sans catégorie", "code": r["categorie__code"] or "",
                                        "compte_comptable": r["categorie__compte_comptable"] or "", "sens": r["type"]}
        lignes = []
        for cid, par_mois in matrice.items():
            lignes.append({**infos[cid], "mois": {m: par_mois.get(m, 0.0) for m in cle_mois}, "total": sum(par_mois.values())})
        lignes.sort(key=lambda x: (x["sens"] != "recette", -x["total"]))
        par_compte = []
        for c in CompteTresorerie.objects.all():
            debut = c.solde_annee(annee, dd - dt.timedelta(days=1))
            fin = c.solde_annee(annee, df)
            par_compte.append({"compte": c.nom, "type": c.get_type_display(), "solde_debut": float(debut), "solde_fin": float(fin),
                               "variation": float(fin - debut)})
        return Response({
            "date_debut": dd, "date_fin": df, "mois": cle_mois, "par_mois": mois, "categories": lignes,
            "totaux": {"recettes": sum(m["recettes"] for m in mois), "depenses": sum(m["depenses"] for m in mois)},
            "comptes": par_compte,
            "par_mode": [{"mode": dict(Operation.MODES).get(r["mode"], r["mode"]), "type": r["type"], "montant": float(r["t"]), "nombre": r["n"]}
                         for r in val.filter(type__in=[Operation.RECETTE, Operation.DEPENSE]).values("mode", "type").annotate(t=Sum("montant"), n=Count("id"))],
        })


# ---------------------------------------------------------------------------
SALAIRES = ("SAL", "CHS", "VAC")


class RecapAnneesView(APIView):
    """Récapitulatif financier par année académique.

    Une opération appartient à une année par son champ année académique, sinon par sa date (période de l'année).
    GET ?detail=<id année> : ajoute l'évolution mensuelle et le recouvrement par classe de cette année.
    """
    permission_classes = [DroitFinance]

    @staticmethod
    def _ops(annee, dd, df):
        return Operation.objects.filter(annee_academique=annee)

    def get(self, request):
        from academique.models import AnneeAcademique
        initialiser()
        today = timezone.localdate()
        annees = sorted(AnneeAcademique.objects.all(), key=lambda a: (a.date_debut or dt.date.min, a.libelle))
        detail_id = request.query_params.get("detail")
        if not detail_id:
            active = next((a for a in annees if a.est_active), annees[-1] if annees else None)
            detail_id = active.id if active else None
        comptes = list(CompteTresorerie.objects.all())
        res = []
        for a in annees:
            dd, df = periode_annee(a)
            ops = self._ops(a, dd, df)
            val = ops.filter(statut=Operation.VALIDEE)
            somme = lambda qs: float(qs.aggregate(t=Sum("montant"))["t"] or 0)  # noqa: E731
            rec = val.filter(type=Operation.RECETTE)
            dep = val.filter(type=Operation.DEPENSE)
            r_ins = somme(rec.filter(categorie__code="SCO-INS"))
            r_for = somme(rec.filter(categorie__code="SCO-FOR"))
            r_tot = somme(rec)
            d_sal = somme(dep.filter(categorie__code__in=SALAIRES))
            d_tot = somme(dep)
            classes = recouvrement(a)
            attendu = sum(c["attendu"] for c in classes)
            encaisse = sum(c["encaisse"] for c in classes)
            budget = Budget.objects.filter(annee_academique=a).first()
            bud = None
            if budget:
                lignes = budget.lignes.select_related("categorie")
                bud = {s: float(sum(l.montant_prevu for l in lignes if l.categorie.sens == s)) for s in ("recette", "depense")}
            fin = min(df, today)
            attente = ops.filter(statut__in=[Operation.EN_ATTENTE, Operation.APPROUVEE])
            par_cat = lambda qs: [  # noqa: E731
                {"categorie": r["categorie__libelle"] or "Sans catégorie", "code": r["categorie__code"] or "", "montant": float(r["t"])}
                for r in qs.values("categorie__libelle", "categorie__code").annotate(t=Sum("montant")).order_by("-t")
            ]
            ligne = {
                "id": a.id, "libelle": a.libelle, "est_active": a.est_active, "date_debut": dd, "date_fin": df,
                "statut": "a_venir" if dd > today else ("en_cours" if df >= today else "terminee"),
                "recettes": {"total": r_tot, "inscription": r_ins, "formation": r_for, "scolarite": r_ins + r_for, "autres": r_tot - r_ins - r_for},
                "depenses": {"total": d_tot, "salaires": d_sal, "autres": d_tot - d_sal},
                "resultat": r_tot - d_tot,
                "scolarite": {
                    "effectif": sum(c["effectif"] for c in classes), "soldes": sum(c["soldes"] for c in classes),
                    "attendu": attendu, "encaisse": encaisse, "reste": max(0.0, attendu - encaisse),
                    "taux": round(encaisse * 100 / attendu, 1) if attendu else 0,
                },
                "budget": {"recettes_prevues": bud["recette"], "depenses_prevues": bud["depense"]} if bud else None,
                "tresorerie_fin": float(sum(c.solde_annee(a, fin) for c in comptes)) if dd <= today else None,
                "reports": {
                    "recus": somme(val.filter(type=Operation.REPORT)),
                    "cedes": somme(Operation.objects.filter(statut=Operation.VALIDEE, type=Operation.REPORT, annee_origine=a)),
                },
                "en_attente": {
                    "recettes": somme(attente.filter(type=Operation.RECETTE)), "depenses": somme(attente.filter(type=Operation.DEPENSE)),
                    "nombre": attente.count(),
                },
                "recettes_par_categorie": par_cat(rec),
                "depenses_par_categorie": par_cat(dep),
                "nb_operations": val.count(),
            }
            if str(a.id) == str(detail_id):
                ligne["par_mois"] = _par_mois(val, dd, df)
                ligne["classes"] = classes
            res.append(ligne)
        return Response({"annees": res, "detail": int(detail_id) if detail_id else None})



class ReportsView(APIView):
    """Reprise de l'argent d'une année académique (précédente) pour une autre.

    GET ?annee=<destination> : reports reçus et cédés par l'année + argent disponible dans les autres années.
    POST {annee_origine, annee?, lignes: [{compte, montant}], commentaire} : crée un report par compte.
    L'argent quitte l'année d'origine et entre dans l'année de destination (le total physique ne change pas).
    """
    permission_classes = [DroitFinance]

    def get(self, request):
        from academique.models import AnneeAcademique
        annee = _annee(request)
        recus = Operation.objects.filter(type=Operation.REPORT, annee_academique=annee).select_related("compte", "annee_origine", "annee_academique")
        cedes = Operation.objects.filter(type=Operation.REPORT, annee_origine=annee).select_related("compte", "annee_origine", "annee_academique")
        comptes = list(CompteTresorerie.objects.filter(actif=True))
        autres = []
        for a in sorted(AnneeAcademique.objects.exclude(pk=getattr(annee, "id", None)), key=lambda x: (x.date_debut or dt.date.min, x.libelle), reverse=True):
            dispo = [{"compte": c.id, "nom": c.nom, "disponible": float(c.solde_annee(a))} for c in comptes]
            autres.append({"id": a.id, "libelle": a.libelle, "date_fin": a.date_fin,
                           "precedente": bool(annee and a.date_fin and annee.date_debut and a.date_fin <= annee.date_debut),
                           "comptes": dispo, "total": sum(d["disponible"] for d in dispo)})
        ctx = {"request": request}
        return Response({
            "annee": {"id": annee.id, "libelle": annee.libelle} if annee else None,
            "recus": OperationSerializer(recus, many=True, context=ctx).data,
            "cedes": OperationSerializer(cedes, many=True, context=ctx).data,
            "annees": autres,
        })

    def post(self, request):
        from academique.models import AnneeAcademique
        dest = get_object_or_404(AnneeAcademique, pk=request.data.get("annee")) if request.data.get("annee") else _annee(request)
        origine = get_object_or_404(AnneeAcademique, pk=request.data.get("annee_origine"))
        if not dest or dest.id == origine.id:
            raise ValidationError({"annee_origine": ["Choisissez une autre année que l'année en cours de gestion."]})
        lignes = [l for l in (request.data.get("lignes") or []) if l.get("compte") and Decimal(str(l.get("montant") or 0)) > 0]
        if not lignes:
            raise ValidationError({"lignes": ["Indiquez au moins un montant à reprendre."]})
        date = _date(request.data.get("date")) or timezone.localdate()
        commentaire = str(request.data.get("commentaire") or "")
        crees = []
        with transaction.atomic():
            for l in lignes:
                compte = get_object_or_404(CompteTresorerie, pk=l["compte"])
                montant = Decimal(str(l["montant"]))
                dispo = compte.solde_annee(origine)
                if montant > dispo:
                    raise ValidationError({"lignes": [f"{compte.nom} : seulement {dispo:,.0f} FCFA disponibles en {origine.libelle}.".replace(",", " ")]})
                crees.append(creer_operation(
                    type=Operation.REPORT, date=date, montant=montant, compte=compte, annee_academique=dest, annee_origine=origine,
                    libelle=f"Report de {origine.libelle} vers {dest.libelle} — {compte.nom}", notes=commentaire,
                    statut=Operation.VALIDEE, source="manuel", mode="autre", cree_par=request.user, valide_par=request.user,
                    valide_le=timezone.now(), approuve_par=request.user, approuve_le=timezone.now(),
                ))
        return Response(OperationSerializer(crees, many=True, context={"request": request}).data, status=status.HTTP_201_CREATED)

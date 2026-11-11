"""Demandes de documents officiels (certificat de scolarité, relevé de notes, carte d'étudiant).

L'étudiant ne télécharge pas ses documents : il en fait la demande depuis son portail ;
l'administration génère, imprime et lui remet le document.

GET    /api/demandes-documents/                     étudiant : ses demandes · personnel : toutes (?statut=&type=&q=)
POST   /api/demandes-documents/                     étudiant : {type, nombre, motif}
DELETE /api/demandes-documents/{id}/                étudiant : retirer une demande encore en attente
POST   /api/demandes-documents/{id}/generer/        personnel : génère le document (données du PDF) → « prêt à retirer »
POST   /api/demandes-documents/{id}/remettre/       personnel : document remis à l'étudiant
POST   /api/demandes-documents/{id}/rejeter/        personnel : {reponse}
GET    /api/demandes-documents/compteurs/           personnel : nombre de demandes par statut
"""
import logging

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .models import DemandeDocument, DocumentDelivre
from .services import DelivranceImpossible, annee_de_reference, document_json, emettre, etablissement_json

logger = logging.getLogger(__name__)


def _profil(user):
    from notifications.services import profil
    return profil(user)


def _nom(u):
    if not u:
        return ""
    return f"{getattr(u, 'prenoms', '') or ''} {getattr(u, 'noms', '') or ''}".strip() or u.username


class DemandeDocumentSerializer(serializers.ModelSerializer):
    type_libelle = serializers.CharField(source="get_type_display", read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    annee_libelle = serializers.CharField(source="annee_academique.libelle", read_only=True, default="")
    document_numero = serializers.CharField(source="document.numero", read_only=True, default="")
    traite_par_nom = serializers.SerializerMethodField()
    classe_nom = serializers.SerializerMethodField()

    class Meta:
        model = DemandeDocument
        fields = [
            "id", "reference", "type", "type_libelle", "nombre", "motif", "statut", "statut_libelle", "reponse",
            "etudiant", "etudiant_nom", "etudiant_matricule", "classe_nom", "annee_academique", "annee_libelle",
            "document", "document_numero", "cree_le", "traite_le", "traite_par_nom", "remise_le",
        ]
        read_only_fields = [f for f in fields if f not in ("type", "nombre", "motif")]

    def get_traite_par_nom(self, obj):
        return _nom(obj.traite_par)

    def get_classe_nom(self, obj):
        from .services import inscription_de
        ins = inscription_de(obj.etudiant, obj.annee_academique)
        return ins.classe.nom if ins and ins.classe_id else ""

    def validate_nombre(self, v):
        if not 1 <= v <= 5:
            raise serializers.ValidationError("Entre 1 et 5 exemplaires.")
        return v


def _notifier_etudiant(demande, titre, message, niveau="info"):
    try:
        from notifications.services import notifier_utilisateurs
        user = getattr(demande.etudiant, "user", None)
        if user:
            notifier_utilisateurs([user], "etudiant", "demande_document", titre, message, lien="/portal/documents",
                                  niveau=niveau, cle=f"demande-doc-{demande.pk}-{demande.statut}")
    except Exception:  # noqa: BLE001 — la notification ne doit jamais bloquer le traitement
        logger.exception("Notification de demande de document")


class DemandeDocumentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                             mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = DemandeDocumentSerializer

    def _etudiant(self):
        if _profil(self.request.user) != "etudiant":
            return None
        return getattr(self.request.user, "etudiant_profile", None)

    def _personnel(self):
        # 404 plutôt que 403 : l'intercepteur du front déconnecte sur 403
        if _profil(self.request.user) != "personnel":
            raise NotFound("Réservé à l'administration.")

    def get_queryset(self):
        qs = DemandeDocument.objects.select_related("etudiant", "annee_academique", "document", "traite_par")
        etu = self._etudiant()
        if etu is not None:
            return qs.filter(etudiant=etu)
        if _profil(self.request.user) != "personnel":
            return qs.none()
        p = self.request.query_params
        if p.get("statut"):
            qs = qs.filter(statut__in=p["statut"].split(","))
        if p.get("type"):
            qs = qs.filter(type=p["type"])
        if p.get("etudiant"):
            qs = qs.filter(etudiant_id=p["etudiant"])
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(reference__icontains=q) | Q(etudiant__nom__icontains=q) | Q(etudiant__matricule__icontains=q))
        return qs

    def perform_create(self, serializer):
        etu = self._etudiant()
        if etu is None:
            raise ValidationError({"detail": "Seuls les étudiants peuvent faire une demande depuis leur portail."})
        t = serializer.validated_data["type"]
        if DemandeDocument.objects.filter(etudiant=etu, type=t, statut__in=[DemandeDocument.EN_ATTENTE, DemandeDocument.PRETE]).exists():
            raise ValidationError({"detail": "Vous avez déjà une demande en cours pour ce document."})
        d = serializer.save(etudiant=etu, annee_academique=annee_de_reference())
        try:
            from notifications.services import notifier
            notifier(["etudiants"], "demande_document", f"Demande de {d.get_type_display().lower()}",
                     f"{etu.nom}{f' ({etu.matricule})' if etu.matricule else ''} — {d.nombre} exemplaire(s)"
                     f"{f' · {d.motif}' if d.motif else ''}", lien="/students/documents", inclure_auteur=True)
        except Exception:  # noqa: BLE001
            logger.exception("Notification de nouvelle demande de document")

    def perform_destroy(self, instance):
        if self._etudiant() is None:
            raise ValidationError({"detail": "L'administration rejette une demande au lieu de la supprimer."})
        if instance.statut != DemandeDocument.EN_ATTENTE:
            raise ValidationError({"detail": "Cette demande est déjà traitée par l'administration."})
        instance.delete()

    def _traiter(self, d, statut, reponse=None):
        d.statut = statut
        d.traite_le = d.traite_le or timezone.now()
        d.traite_par = self.request.user
        if reponse is not None:
            d.reponse = str(reponse)[:255]
        if statut == DemandeDocument.REMISE:
            d.remise_le = timezone.now()
        d.save()

    @action(detail=True, methods=["post"])
    def generer(self, request, pk=None):
        """Génère le document demandé. Certificat et carte : inscription au registre (numéro, QR) et données du PDF.
        Relevé : le front le produit à partir de /api/notes/{etudiant}/releve-notes/."""
        self._personnel()
        d = self.get_object()
        if d.statut in (DemandeDocument.REJETEE, DemandeDocument.REMISE) and not request.data.get("forcer"):
            return Response({"detail": "Cette demande est clôturée."}, status=400)
        payload = {"type": d.type, "etudiant": d.etudiant_id, "nombre": d.nombre}
        if d.type in (DocumentDelivre.CERTIFICAT, DocumentDelivre.CARTE):
            try:
                doc, _ = emettre(d.type, d.etudiant, request.user, "administration", False, annee=d.annee_academique)
            except DelivranceImpossible as e:
                return Response({"detail": str(e), "conditions": e.conditions}, status=400)
            d.document = doc
            payload.update({"etablissement": etablissement_json(), "documents": [document_json(doc)]})
        if d.statut == DemandeDocument.EN_ATTENTE:
            self._traiter(d, DemandeDocument.PRETE, request.data.get("reponse") or "Votre document est prêt : retirez-le à la scolarité.")
            _notifier_etudiant(d, f"{d.get_type_display()} prêt", d.reponse, niveau="succes")
        else:
            d.save()
        payload["demande"] = DemandeDocumentSerializer(d).data
        return Response(payload)

    @action(detail=True, methods=["post"])
    def remettre(self, request, pk=None):
        self._personnel()
        d = self.get_object()
        if d.statut == DemandeDocument.REJETEE:
            return Response({"detail": "Cette demande a été rejetée."}, status=400)
        self._traiter(d, DemandeDocument.REMISE)
        return Response(DemandeDocumentSerializer(d).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        self._personnel()
        d = self.get_object()
        reponse = str(request.data.get("reponse") or "").strip()
        if not reponse:
            return Response({"detail": "Indiquez le motif du rejet : il est communiqué à l'étudiant."}, status=400)
        if d.statut == DemandeDocument.REMISE:
            return Response({"detail": "Le document a déjà été remis."}, status=400)
        self._traiter(d, DemandeDocument.REJETEE, reponse)
        _notifier_etudiant(d, f"Demande de {d.get_type_display().lower()} refusée", reponse, niveau="alerte")
        return Response(DemandeDocumentSerializer(d).data)

    @action(detail=False, methods=["get"])
    def compteurs(self, request):
        self._personnel()
        data = dict(DemandeDocument.objects.values_list("statut").annotate(n=Count("id")))
        return Response({s: data.get(s, 0) for s, _ in DemandeDocument.STATUTS})

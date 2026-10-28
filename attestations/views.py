from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DocumentDelivre
from .serializers import DocumentDelivreSerializer
from .services import (
    DelivranceImpossible, annee_de_reference, document_json, emettre, etablissement_json, statut,
)


class Pagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


def _profil(user):
    from notifications.services import profil
    return profil(user)


class DocumentDelivreViewSet(viewsets.ReadOnlyModelViewSet):
    """Certificats de scolarité et cartes d'étudiant.

    GET  /api/documents-officiels/?type=&classe=&annee=&statut=&q=     registre (personnel)
    POST /api/documents-officiels/emettre/          {type, etudiant, nouveau?}
    POST /api/documents-officiels/emettre-classe/   {type, classe, nouveau?}
    POST /api/documents-officiels/mes-documents/    {type}       (étudiant connecté, inscrit)
    POST /api/documents-officiels/{id}/reimprimer/
    POST /api/documents-officiels/{id}/annuler/     {motif}
    """

    serializer_class = DocumentDelivreSerializer
    pagination_class = Pagination

    def _personnel(self):
        if _profil(self.request.user) != "personnel":
            raise PermissionDenied("Réservé à l'administration.")

    def get_queryset(self):
        self._personnel()
        qs = DocumentDelivre.objects.select_related("etudiant", "classe", "annee_academique", "delivre_par")
        p = self.request.query_params
        if p.get("type"):
            qs = qs.filter(type=p["type"])
        if p.get("classe"):
            qs = qs.filter(classe_id=p["classe"])
        if p.get("annee"):
            qs = qs.filter(annee_academique_id=p["annee"])
        if p.get("etudiant"):
            qs = qs.filter(etudiant_id=p["etudiant"])
        if p.get("q"):
            q = p["q"].strip()
            qs = qs.filter(Q(numero__icontains=q) | Q(etudiant__nom__icontains=q) | Q(etudiant__matricule__icontains=q))
        st = p.get("statut")
        today = timezone.localdate()
        if st == "annule":
            qs = qs.filter(annule=True)
        elif st == "valide":
            qs = qs.filter(annule=False).filter(Q(valide_jusqu_au__isnull=True) | Q(valide_jusqu_au__gte=today))
        elif st == "expire":
            qs = qs.filter(annule=False, valide_jusqu_au__lt=today)
        return qs

    def _type(self, request):
        t = request.data.get("type")
        if t not in (DocumentDelivre.CERTIFICAT, DocumentDelivre.CARTE):
            raise DelivranceImpossible("Type de document inconnu (certificat ou carte).")
        return t

    @action(detail=False, methods=["post"])
    def emettre(self, request):
        from etudiants.models import Etudiant
        self._personnel()
        try:
            t = self._type(request)
            etu = get_object_or_404(Etudiant, pk=request.data.get("etudiant"))
            doc, cree = emettre(t, etu, request.user, "administration", bool(request.data.get("nouveau")))
        except DelivranceImpossible as e:
            return Response({"detail": str(e)}, status=400)
        return Response({"etablissement": etablissement_json(), "documents": [document_json(doc)], "nouveaux": int(cree)})

    @action(detail=False, methods=["post"], url_path="emettre-classe")
    def emettre_classe(self, request):
        from academique.models import Classe
        from etudiants.models import Etudiant
        self._personnel()
        try:
            t = self._type(request)
        except DelivranceImpossible as e:
            return Response({"detail": str(e)}, status=400)
        classe = get_object_or_404(Classe, pk=request.data.get("classe"))
        annee = classe.annee_academique
        etudiants = Etudiant.objects.filter(inscriptions__classe=classe).distinct().order_by("nom")
        docs, ignores, nouveaux = [], [], 0
        for etu in etudiants:
            try:
                doc, cree = emettre(t, etu, request.user, "administration", bool(request.data.get("nouveau")), annee=annee)
                docs.append(document_json(doc))
                nouveaux += int(cree)
            except DelivranceImpossible as e:
                ignores.append(str(e))
        if not docs:
            return Response({"detail": "Aucun étudiant inscrit dans cette classe.", "ignores": ignores}, status=400)
        return Response({"etablissement": etablissement_json(), "documents": docs, "ignores": ignores, "nouveaux": nouveaux})

    @action(detail=False, methods=["post"], url_path="mes-documents")
    def mes_documents(self, request):
        etu = getattr(request.user, "etudiant_profile", None) if _profil(request.user) == "etudiant" else None
        if etu is None:
            raise PermissionDenied("Réservé aux étudiants.")
        try:
            t = self._type(request)
            doc, cree = emettre(t, etu, request.user, "portail", False)
        except DelivranceImpossible as e:
            return Response({"detail": str(e), "inscrit": False}, status=403)
        return Response({"etablissement": etablissement_json(), "documents": [document_json(doc)], "nouveaux": int(cree)})

    @action(detail=True, methods=["post"])
    def reimprimer(self, request, pk=None):
        doc = self.get_object()
        if doc.annule:
            return Response({"detail": "Ce document est annulé : délivrez-en un nouveau."}, status=400)
        doc.nb_impressions += 1
        doc.derniere_impression = timezone.now()
        doc.save(update_fields=["nb_impressions", "derniere_impression"])
        return Response({"etablissement": etablissement_json(), "documents": [document_json(doc)], "nouveaux": 0})

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        doc = self.get_object()
        if doc.annule:
            return Response({"detail": "Déjà annulé."}, status=400)
        doc.annule, doc.annule_le, doc.annule_par = True, timezone.now(), request.user
        doc.motif_annulation = str(request.data.get("motif") or "Annulé par l'administration")[:255]
        doc.save(update_fields=["annule", "annule_le", "annule_par", "motif_annulation"])
        return Response(DocumentDelivreSerializer(doc).data)

    @action(detail=False, methods=["get"], url_path="eligibilite")
    def eligibilite(self, request):
        """Étudiant connecté : peut-il télécharger ses documents ?"""
        from .services import inscription_de
        etu = getattr(request.user, "etudiant_profile", None) if _profil(request.user) == "etudiant" else None
        if etu is None:
            raise PermissionDenied("Réservé aux étudiants.")
        annee = annee_de_reference()
        ins = inscription_de(etu, annee)
        return Response({
            "annee": annee.libelle if annee else None,
            "inscrit": bool(ins and ins.statut == "Inscrit"),
            "statut": ins.statut if ins else None,
            "classe": ins.classe.nom if ins and ins.classe_id else None,
        })


class VerificationView(APIView):
    """Vérification publique d'un document par son code (QR code). Aucune connexion requise."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, code):
        from academique.models import ConfigurationEtablissement
        doc = DocumentDelivre.objects.select_related("etudiant", "classe", "annee_academique").filter(code=code).first()
        c = ConfigurationEtablissement.get_config()
        etab = {"nom": c.nom, "ville": c.ville, "telephone": c.telephone, "email": c.email,
                "logo": request.build_absolute_uri(c.logo.url) if c.logo else None}
        if not doc:
            return Response({"trouve": False, "etablissement": etab}, status=status.HTTP_404_NOT_FOUND)
        d = doc.donnees or {}
        return Response({
            "trouve": True,
            "etablissement": etab,
            "type": doc.type, "type_libelle": doc.get_type_display(), "numero": doc.numero,
            "statut": statut(doc), "motif_annulation": doc.motif_annulation if doc.annule else "",
            "delivre_le": doc.delivre_le, "valide_jusqu_au": doc.valide_jusqu_au,
            "etudiant": {"nom": d.get("nom"), "matricule": d.get("matricule"), "classe": d.get("classe"),
                         "filiere": d.get("filiere"), "niveau": d.get("niveau")},
            "annee_academique": d.get("annee_academique"),
            "resultats": d.get("resultats") if doc.type == DocumentDelivre.RELEVE else None,
        })

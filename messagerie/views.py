import os

from django.db.models import Count, F, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from notifications.services import notifier_utilisateurs, profil

from . import acces
from .models import Conversation, Lecture, Message

TAILLE_MAX = 10 * 1024 * 1024
LIBELLES_SERVICE = dict(Conversation.SERVICES)


def nom_utilisateur(u):
    if u is None:
        return "Utilisateur supprimé"
    p = profil(u)
    if p == "etudiant":
        return u.etudiant_profile.nom
    if p == "formateur":
        return u.formateur_profile.nom
    nom = f"{getattr(u, 'prenoms', '') or ''} {getattr(u, 'noms', '') or ''}".strip()
    return nom or u.get_full_name() or u.username


def libelle_conv(conv, user):
    p = profil(user)
    if conv.type == Conversation.SERVICE:
        service = LIBELLES_SERVICE.get(conv.service, conv.service)
        if p == "etudiant":
            return service, "Échange privé avec l'administration"
        etu = conv.etudiant
        return etu.nom if etu else "Étudiant", f"{service} · {getattr(etu, 'matricule', '')}"
    module = getattr(conv.module, "nom", "")
    classe = getattr(conv.classe, "nom", "")
    if p == "etudiant":
        noms = ", ".join(f.nom for f in acces.formateurs_de(conv.classe_id, conv.module_id)[:2])
        return module, noms or "Formateur"
    return f"{module} — {classe}", "Classe ↔ formateur"


def message_json(m, request, user):
    pj = None
    if m.piece_jointe:
        pj = {"url": request.build_absolute_uri(m.piece_jointe.url), "nom": os.path.basename(m.piece_jointe.name)}
    return {
        "id": m.id,
        "texte": m.texte,
        "piece_jointe": pj,
        "cree_le": m.cree_le,
        "moi": m.auteur_id == user.id,
        "auteur": {"id": m.auteur_id, "nom": nom_utilisateur(m.auteur), "profil": profil(m.auteur) if m.auteur else None},
    }


class ConversationViewSet(viewsets.GenericViewSet):
    """Messagerie interne.

    GET  /api/messagerie/conversations/                    (?q=)
    GET  /api/messagerie/conversations/non-lus/
    POST /api/messagerie/conversations/ouvrir/             {type:"service", service, etudiant} | {type:"classe", classe, module}
    GET  /api/messagerie/conversations/{id}/messages/      (?apres=<id> | ?avant=<id>)
    POST /api/messagerie/conversations/{id}/messages/      texte, piece_jointe (multipart)
    POST /api/messagerie/conversations/{id}/lire/
    GET  /api/messagerie/conversations/etudiants/?q=       (personnel : démarrer un échange)
    """

    parser_classes = [JSONParser, MultiPartParser, FormParser]
    queryset = Conversation.objects.all()

    def _avec_compteurs(self, qs, user):
        dernier_lu = Lecture.objects.filter(conversation=OuterRef("pk"), utilisateur=user).values("dernier_lu")[:1]
        return qs.annotate(_lu=Coalesce(Subquery(dernier_lu), Value(0))).annotate(
            non_lus=Count("messages", filter=Q(messages__id__gt=F("_lu")) & ~Q(messages__auteur=user), distinct=True),
        )

    def _conv(self, pk):
        conv = get_object_or_404(Conversation.objects.select_related("etudiant", "classe", "module"), pk=pk)
        if not acces.peut_acceder(self.request.user, conv):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Vous n'avez pas accès à cette conversation.")
        return conv

    def _resume(self, conv, user):
        titre, sous_titre = libelle_conv(conv, user)
        dernier = conv.messages.select_related("auteur").last()
        return {
            "id": conv.id,
            "type": conv.type,
            "service": conv.service,
            "titre": titre,
            "sous_titre": sous_titre,
            "non_lus": getattr(conv, "non_lus", 0) or 0,
            "dernier_message": {
                "texte": dernier.texte or ("📎 " + os.path.basename(dernier.piece_jointe.name) if dernier.piece_jointe else ""),
                "auteur": "Vous" if dernier.auteur_id == user.id else nom_utilisateur(dernier.auteur),
                "cree_le": dernier.cree_le,
            } if dernier else None,
            "dernier_message_le": conv.dernier_message_le,
        }

    def list(self, request):
        qs = acces.conversations_visibles(request.user).select_related("etudiant", "classe", "module")
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(etudiant__nom__icontains=q) | Q(etudiant__matricule__icontains=q)
                | Q(classe__nom__icontains=q) | Q(module__nom__icontains=q)
            )
        qs = self._avec_compteurs(qs, request.user).order_by("-dernier_message_le", "type", "id")[:200]
        return Response([self._resume(c, request.user) for c in qs])

    @action(detail=False, methods=["get"], url_path="non-lus")
    def non_lus(self, request):
        qs = self._avec_compteurs(acces.conversations_visibles(request.user), request.user)
        return Response({"total": sum(c.non_lus for c in qs)})

    @action(detail=False, methods=["post"])
    def ouvrir(self, request):
        d = request.data
        if d.get("type") == Conversation.CLASSE:
            conv, _ = Conversation.objects.get_or_create(type=Conversation.CLASSE, classe_id=d.get("classe"), module_id=d.get("module"))
        else:
            service = d.get("service")
            if service not in acces.DOMAINE_SERVICE:
                return Response({"detail": "Service inconnu."}, status=400)
            etudiant_id = d.get("etudiant")
            if profil(request.user) == "etudiant":
                etudiant_id = acces.etudiant_de(request.user).id
            elif service not in acces.services_accessibles(request.user):
                return Response({"detail": "Ce service ne fait pas partie de vos droits."}, status=403)
            from etudiants.models import Etudiant
            etu = get_object_or_404(Etudiant, pk=etudiant_id)
            conv, _ = Conversation.objects.get_or_create(type=Conversation.SERVICE, etudiant=etu, service=service)
        conv = self._conv(conv.pk)
        conv.non_lus = 0
        return Response(self._resume(conv, request.user))

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        conv = self._conv(pk)
        user = request.user
        if request.method == "POST":
            texte = (request.data.get("texte") or "").strip()
            fichier = request.FILES.get("piece_jointe")
            if not texte and not fichier:
                return Response({"detail": "Message vide."}, status=400)
            if fichier and fichier.size > TAILLE_MAX:
                return Response({"detail": "Pièce jointe trop volumineuse (10 Mo maximum)."}, status=400)
            m = Message.objects.create(conversation=conv, auteur=user, texte=texte[:5000], piece_jointe=fichier)
            conv.dernier_message_le = m.cree_le
            conv.save(update_fields=["dernier_message_le"])
            Lecture.objects.update_or_create(conversation=conv, utilisateur=user, defaults={"dernier_lu": m.id})
            self._prevenir(conv, m)
            return Response(message_json(m, request, user), status=status.HTTP_201_CREATED)

        qs = conv.messages.select_related("auteur", "auteur__etudiant_profile", "auteur__formateur_profile")
        p = request.query_params
        if p.get("apres"):
            msgs = list(qs.filter(id__gt=int(p["apres"]))[:200])
            plus = False
        else:
            if p.get("avant"):
                qs = qs.filter(id__lt=int(p["avant"]))
            derniers = list(qs.order_by("-id")[:51])
            plus = len(derniers) > 50
            msgs = list(reversed(derniers[:50]))
        return Response({"messages": [message_json(m, request, user) for m in msgs], "plus_anciens": plus})

    @action(detail=True, methods=["post"])
    def lire(self, request, pk=None):
        conv = self._conv(pk)
        dernier = conv.messages.aggregate(m=Max("id"))["m"] or 0
        Lecture.objects.update_or_create(conversation=conv, utilisateur=request.user, defaults={"dernier_lu": dernier})
        return Response({"dernier_lu": dernier})

    @action(detail=False, methods=["get"])
    def etudiants(self, request):
        """Recherche d'étudiants pour démarrer un échange (personnel uniquement)."""
        if profil(request.user) != "personnel" or not acces.services_accessibles(request.user):
            return Response([])
        from etudiants.models import Etudiant
        q = (request.query_params.get("q") or "").strip()
        qs = Etudiant.objects.all()
        if q:
            qs = qs.filter(Q(nom__icontains=q) | Q(matricule__icontains=q) | Q(email__icontains=q))
        res = []
        for e in qs.order_by("nom")[:20]:
            classe = acces.classe_courante(e)
            res.append({"id": e.id, "nom": e.nom, "matricule": e.matricule, "classe": classe.nom if classe else "", "a_un_compte": bool(e.user_id)})
        return Response({"etudiants": res, "services": acces.services_accessibles(request.user)})

    def _prevenir(self, conv, m):
        auteur = self.request.user
        titre_conv, _ = libelle_conv(conv, auteur)
        nom = nom_utilisateur(auteur)
        extrait = (m.texte or "Pièce jointe").replace("\n", " ")
        extrait = extrait[:140] + ("…" if len(extrait) > 140 else "")
        users = acces.a_prevenir(conv, auteur)
        liens = {"etudiant": "/portal/messages", "formateur": "/trainer/messages", "personnel": "/messagerie"}
        par_lien = {}
        for u in users:
            par_lien.setdefault(liens[profil(u)], []).append(u)
        for lien, groupe in par_lien.items():
            if conv.type == Conversation.SERVICE and lien != "/messagerie":
                titre = f"Message de l'administration ({LIBELLES_SERVICE.get(conv.service)})"
            elif conv.type == Conversation.SERVICE:
                titre = f"{nom} · {LIBELLES_SERVICE.get(conv.service)}"
            else:
                titre = f"{nom} · {getattr(conv.module, 'nom', '')}"
            # Une seule notification non lue par conversation et par minute pour éviter le bruit
            cle = f"msg-{conv.id}-{timezone.now():%Y%m%d%H%M}"
            notifier_utilisateurs(groupe, "messages", "message", titre, extrait, lien=f"{lien}?c={conv.id}", cle=cle)

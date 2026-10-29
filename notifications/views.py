from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import viewsets

from .models import AbonnementPush, Notification, PreferenceNotification
from .serializers import NotificationSerializer
from .services import categories_utilisateur, push_configure


class Pagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 200


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """Notifications de l'utilisateur connecté.

    GET  /api/notifications/?non_lues=1&categorie=finance
    GET  /api/notifications/compteur/
    POST /api/notifications/{id}/lire/        POST /api/notifications/tout-lire/
    DELETE /api/notifications/{id}/supprimer/
    GET/PUT /api/notifications/preferences/
    GET  /api/notifications/push/cle-publique/
    POST /api/notifications/push/abonnement/  (body : PushSubscription JSON)   DELETE (body : {endpoint})
    """

    serializer_class = NotificationSerializer
    pagination_class = Pagination

    def get_queryset(self):
        qs = Notification.objects.filter(destinataire=self.request.user)
        p = self.request.query_params
        if p.get("non_lues") in ("1", "true"):
            qs = qs.filter(lu=False)
        if p.get("categorie"):
            qs = qs.filter(categorie=p["categorie"])
        return qs

    @action(detail=False, methods=["get"])
    def compteur(self, request):
        # Les rappels périodiques sont déclenchés ici à défaut de tâche planifiée (au plus toutes les 6 h)
        try:
            from .verifications import executer
            executer()
        except Exception:  # noqa: BLE001
            pass
        qs = Notification.objects.filter(destinataire=request.user)
        derniere = qs.first()
        return Response({
            "non_lues": qs.filter(lu=False).count(),
            "derniere_id": derniere.id if derniere else None,
        })

    @action(detail=True, methods=["post"])
    def lire(self, request, pk=None):
        n = self.get_object()
        if not n.lu:
            n.lu, n.lu_le = True, timezone.now()
            n.save(update_fields=["lu", "lu_le"])
        return Response(NotificationSerializer(n).data)

    @action(detail=False, methods=["post"], url_path="tout-lire")
    def tout_lire(self, request):
        qs = Notification.objects.filter(destinataire=request.user, lu=False)
        if request.data.get("categorie"):
            qs = qs.filter(categorie=request.data["categorie"])
        nb = qs.update(lu=True, lu_le=timezone.now())
        return Response({"marquees": nb})

    @action(detail=True, methods=["delete"])
    def supprimer(self, request, pk=None):
        self.get_object().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get", "put"])
    def preferences(self, request):
        pref, _ = PreferenceNotification.objects.get_or_create(utilisateur=request.user)
        if request.method == "PUT":
            cats = request.data.get("categories_desactivees", pref.categories_desactivees)
            permises = categories_utilisateur(request.user)
            pref.categories_desactivees = [c for c in (cats or []) if c in permises]
            if "push_actif" in request.data:
                pref.push_actif = bool(request.data.get("push_actif"))
            pref.save()
        permises = categories_utilisateur(request.user)
        return Response({
            "categories_desactivees": pref.categories_desactivees,
            "push_actif": pref.push_actif,
            "categories": [{"code": c, "libelle": l} for c, l in Notification.CATEGORIES if c in permises],
            "appareils": AbonnementPush.objects.filter(utilisateur=request.user).count(),
        })

    @action(detail=False, methods=["get"], url_path="push/cle-publique")
    def cle_publique(self, request):
        from .services import cles_vapid, envoi_disponible
        pub, _priv = cles_vapid()
        return Response({"cle": pub or "", "actif": bool(pub) and envoi_disponible()})

    @action(detail=False, methods=["post", "delete"], url_path="push/abonnement")
    def abonnement(self, request):
        data = request.data or {}
        endpoint = data.get("endpoint")
        if not endpoint:
            return Response({"detail": "Abonnement invalide."}, status=400)
        if request.method == "DELETE":
            AbonnementPush.objects.filter(endpoint=endpoint, utilisateur=request.user).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        keys = data.get("keys") or {}
        if not keys.get("p256dh") or not keys.get("auth"):
            return Response({"detail": "Clés de l'abonnement manquantes."}, status=400)
        AbonnementPush.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                "utilisateur": request.user, "p256dh": keys["p256dh"], "auth": keys["auth"],
                "navigateur": (request.META.get("HTTP_USER_AGENT") or "")[:255],
            },
        )
        return Response({"detail": "Notifications activées sur cet appareil."}, status=201)

    @action(detail=False, methods=["post"], url_path="push/test")
    def test(self, request):
        """Envoie une notification de test à l'utilisateur connecté."""
        from .services import envoyer_push
        n = Notification.objects.create(
            destinataire=request.user, categorie="systeme", type="test", titre="Notification de test",
            message="Les notifications fonctionnent sur cet appareil.", lien="", niveau="succes",
        )
        envoyes = envoyer_push([request.user.id], {"titre": n.titre, "message": n.message, "lien": n.lien, "niveau": n.niveau})
        return Response({"id": n.id, "push_envoyes": envoyes, "push_configure": push_configure()})

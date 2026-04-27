from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils.crypto import get_random_string

from .models import CustomUser, Role
from .serializers import UserSerializer, RoleSerializer


class RoleViewSet(viewsets.ModelViewSet):
    """
    CRUD complet sur les rôles.
    Accessible uniquement aux administrateurs (à protéger avec HasRolePermission si besoin).
    """
    queryset = Role.objects.all().order_by("libelle")
    serializer_class = RoleSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def perform_create(self, serializer):
        user = serializer.save()

        # Générer un mot de passe aléatoire de 8 caractères
        raw_password = get_random_string(8)
        user.set_password(raw_password)
        user._raw_password = raw_password  # exposé via serializer

        # Générer un username si besoin
        if not user.username:
            base_username = f"{user.prenoms.lower()}.{user.noms.lower()}"
            user.username = base_username

        user.save()

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        new_password = get_random_string(8)
        user.set_password(new_password)
        user._raw_password = new_password
        user.save()
        return Response(
            {
                "username": user.username,
                "new_password": new_password,
            },
            status=status.HTTP_200_OK
        )
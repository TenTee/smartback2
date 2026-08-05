# users/permissions.py
from rest_framework.permissions import BasePermission

class HasRolePermission(BasePermission):
    """
    Permission personnalisée qui vérifie le rôle de l'utilisateur.
    Exemple : superAdmin, responsableRh, responsablePedagogique, responsableLogistique
    """

    def has_permission(self, request, view):
        # ⚠️ Ici tu peux adapter la logique selon tes besoins
        if not request.user or not request.user.is_authenticated:
            return False

        # Exemple : seuls les superAdmin peuvent accéder à certaines vues
        if hasattr(view, "required_roles"):
            return request.user.role in view.required_roles

        # Par défaut, autoriser si l'utilisateur est actif
        return request.user.is_active
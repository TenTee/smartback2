from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Autorise la lecture pour tout le monde,
    mais seuls les admins peuvent créer, modifier ou supprimer.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff

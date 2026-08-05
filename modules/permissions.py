from rest_framework.permissions import BasePermission

class IsAdminOrTeacher(BasePermission):
    """
    Autorise si user.role == 'admin' OU role == 'pedagogie' (enseignant).
    Utilisé pour créer/éditer modules.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in ('admin', 'pedagogie'))

    def has_object_permission(self, request, view, obj):
        # Admin full control, teacher only if assigned (optional policy)
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.role == 'admin':
            return True
        # If teacher, only allow if teacher is the owner of the module
        return obj.teacher_id == user.id

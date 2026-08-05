# files/permissions.py
from rest_framework import permissions
from users.permissions import HasRolePermission


class IsAdminOrFinance(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_staff or request.user.groups.filter(name='Finance').exists()

class IsUploaderOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user == obj.uploaded_by or request.user.is_staff
class FileDeletePermission(HasRolePermission):
    allowed_roles = ["admin", "finance"]

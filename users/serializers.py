from rest_framework import serializers
from .models import CustomUser, Role


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "libelle",
            "can_manage_rh",
            "can_manage_pedagogie",
            "can_manage_logistique",
            "can_manage_finance",
            "can_manage_etudiants",
        ]


class UserSerializer(serializers.ModelSerializer):
    raw_password = serializers.CharField(read_only=True, source="_raw_password")
    role_details = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "noms",
            "prenoms",
            "email",
            "role",
            "role_details",
            "username",       # généré automatiquement
            "raw_password",   # mot de passe généré en clair
        ]
        read_only_fields = ["username", "raw_password"]

    def get_role_details(self, obj):
        try:
            # On cherche le rôle dont le code correspond à user.role
            role_obj = Role.objects.get(code=obj.role)
            return RoleSerializer(role_obj).data
        except Role.DoesNotExist:
            return None
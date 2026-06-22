from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
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
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['username'] = user.username
        token['role'] = user.role
        token['is_superuser'] = user.is_superuser
        
        # Add permissions if role exists
        try:
            role_obj = Role.objects.get(code=user.role)
            token['permissions'] = {
                'can_manage_rh': role_obj.can_manage_rh,
                'can_manage_pedagogie': role_obj.can_manage_pedagogie,
                'can_manage_logistique': role_obj.can_manage_logistique,
                'can_manage_finance': role_obj.can_manage_finance,
                'can_manage_etudiants': role_obj.can_manage_etudiants,
            }
        except Role.DoesNotExist:
            if user.is_superuser:
                token['permissions'] = {
                    'can_manage_rh': 'ecriture',
                    'can_manage_pedagogie': 'ecriture',
                    'can_manage_logistique': 'ecriture',
                    'can_manage_finance': 'ecriture',
                    'can_manage_etudiants': 'ecriture',
                }
            else:
                token['permissions'] = {}

        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data

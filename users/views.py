from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils.crypto import get_random_string

from rest_framework_simplejwt.views import TokenObtainPairView
from .models import CustomUser, Role
from .serializers import UserSerializer, RoleSerializer, MyTokenObtainPairSerializer


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
        from django.utils import timezone as _tz
        user.mot_de_passe_provisoire = raw_password
        user.mdp_modifie_par_utilisateur = False
        user.identifiants_maj_le = _tz.now()

        # Générer un username si besoin
        if not user.username:
            base_username = f"{user.prenoms.lower()}.{user.noms.lower()}"
            user.username = base_username

        user.save()

    @action(detail=False, methods=["get"], url_path="moi")
    def moi(self, request):
        """Profil de l'utilisateur connecté (portails étudiant / formateur)."""
        u = request.user
        data = {
            "id": u.id, "noms": u.noms, "prenoms": u.prenoms, "email": u.email,
            "username": u.username, "role": u.role, "is_superuser": u.is_superuser,
            "mot_de_passe_a_changer": bool(getattr(u, "mot_de_passe_provisoire", None)) and not getattr(u, "mdp_modifie_par_utilisateur", False),
        }
        # Droits du rôle (menu de l'espace d'administration), toujours à jour
        from .serializers import CHAMPS_DROITS, niveau_acces
        role_obj = Role.objects.filter(code=u.role).first() if u.role else None
        data["role_libelle"] = role_obj.libelle if role_obj else ("Super administrateur" if u.is_superuser else (u.role or ""))
        data["permissions"] = {
            c: ("ecriture" if u.is_superuser else niveau_acces(getattr(role_obj, c, "none") if role_obj else "none"))
            for c in CHAMPS_DROITS
        }
        etu = getattr(u, "etudiant_profile", None)
        if etu:
            data["etudiant"] = {"id": etu.id, "nom": etu.nom, "matricule": getattr(etu, "matricule", ""),
                                "contact": getattr(etu, "contact", ""), "email": getattr(etu, "email", "")}
        form = getattr(u, "formateur_profile", None)
        if form:
            data["formateur"] = {"id": form.id, "nom": form.nom, "contact": form.contact, "email": form.email,
                                 "type_formateur": form.type_formateur,
                                 "specialites": [m.nom for m in form.specialites.all()]}
        return Response(data)

    @action(detail=False, methods=["post"], url_path="changer-mot-de-passe")
    def changer_mot_de_passe(self, request):
        """Changement de son propre mot de passe : {ancien, nouveau}."""
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        ancien = request.data.get("ancien") or ""
        nouveau = request.data.get("nouveau") or ""
        user = request.user
        if not user.check_password(ancien):
            return Response({"ancien": ["Mot de passe actuel incorrect."]}, status=status.HTTP_400_BAD_REQUEST)
        if len(nouveau) < 8:
            return Response({"nouveau": ["Le nouveau mot de passe doit contenir au moins 8 caractères."]}, status=status.HTTP_400_BAD_REQUEST)
        if nouveau == ancien:
            return Response({"nouveau": ["Le nouveau mot de passe doit être différent de l'actuel."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(nouveau, user)
        except DjangoValidationError as e:
            return Response({"nouveau": list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(nouveau)
        user.mot_de_passe_provisoire = None
        user.mdp_modifie_par_utilisateur = True
        user.save()
        # Le mot de passe choisi par l'utilisateur n'est jamais conservé en clair
        form = getattr(user, "formateur_profile", None)
        if form is not None:
            form.mot_de_passe_initial = None
            form.mdp_modifie_par_formateur = True
            form.save(update_fields=["mot_de_passe_initial", "mdp_modifie_par_formateur"])
        etu = getattr(user, "etudiant_profile", None)
        if etu is not None and getattr(etu, "initial_password", None):
            etu.initial_password = None
            etu.save(update_fields=["initial_password"])
        return Response({"detail": "Mot de passe modifié."})

    @action(detail=True, methods=["get", "post", "patch"], url_path="identifiants")
    def identifiants(self, request, pk=None):
        """Identifiants d'un utilisateur : consulter (GET), réinitialiser (POST
        {mot_de_passe?, nouvel_identifiant?}), activer / suspendre (PATCH {compte_actif})."""
        from .identifiants import appliquer_requete, infos
        user = self.get_object()
        code, data = appliquer_requete(request, user)
        if code != 200:
            return Response(data, status=code)
        user.refresh_from_db()
        return Response(infos(user))

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        from .identifiants import est_admin, reinitialiser
        if not est_admin(request.user):
            return Response({"detail": "Accès réservé à l'administration."}, status=status.HTTP_403_FORBIDDEN)
        user = self.get_object()
        new_password = reinitialiser(user)
        user._raw_password = new_password
        return Response(
            {
                "username": user.username,
                "new_password": new_password,
            },
            status=status.HTTP_200_OK
        )
from rest_framework.permissions import AllowAny
class MyTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = MyTokenObtainPairSerializer

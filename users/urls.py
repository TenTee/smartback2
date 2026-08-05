# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, RoleViewSet

router = DefaultRouter()
router.register(r"roles", RoleViewSet, basename="role")  # /api/users/roles/
router.register(r"", UserViewSet, basename="user")       # /api/users/

urlpatterns = router.urls
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RevenuViewSet

router = DefaultRouter()
router.register(r"revenus", RevenuViewSet)

urlpatterns = [
    path("api/", include(router.urls)),
]
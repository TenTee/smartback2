# conges/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CongeViewSet

router = DefaultRouter()
router.register(r'', CongeViewSet, basename='conge')

urlpatterns = [
    path('', include(router.urls)),
]

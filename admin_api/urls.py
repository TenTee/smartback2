from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProtectedView, StudentViewSet, TrainerViewSet

router = DefaultRouter()
router.register(r'students', StudentViewSet)
router.register(r'trainers', TrainerViewSet)

urlpatterns = [
    path('protected/', ProtectedView.as_view()),  # ton endpoint protégé
    path('', include(router.urls)),               # CRUD Students & Trainers
]


from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NoteViewSet
from .views_partielles import EvaluationPartielleViewSet

router = DefaultRouter()
router.register(r'notes', NoteViewSet, basename='notes')
router.register(r'evaluations-partielles', EvaluationPartielleViewSet, basename='evaluations-partielles')

urlpatterns = [
    path('', include(router.urls)),
]

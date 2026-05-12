from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaieViewSet, ContentTypeView, PaieForecastView

router = DefaultRouter()
router.register(r'paies', PaieViewSet, basename='paies')

urlpatterns = [
    path('', include(router.urls)),
    path('content-types/', ContentTypeView.as_view(), name="content-types"),
    path('forecast/', PaieForecastView.as_view(), name="paie-forecast"),
]
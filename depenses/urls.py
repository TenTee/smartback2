# recufactures/urls.py
from rest_framework.routers import DefaultRouter
from .views import DepenseViewSet

router = DefaultRouter()
router.register(r'depenses', DepenseViewSet, basename='depenses')

urlpatterns = router.urls

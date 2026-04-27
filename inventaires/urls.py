from rest_framework.routers import DefaultRouter
from .views import InventaireViewSet

router = DefaultRouter()
router.register(r'', InventaireViewSet, basename='inventaire')

urlpatterns = router.urls

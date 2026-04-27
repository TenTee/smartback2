from rest_framework.routers import DefaultRouter
from .views import AssiduiteRecordViewSet

router = DefaultRouter()
router.register(r"assiduite", AssiduiteRecordViewSet, basename="assiduite")

urlpatterns = router.urls

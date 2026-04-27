from rest_framework import routers
from .views import EmploiDuTempsViewSet

router = routers.DefaultRouter()
router.register(r'emploi-du-temps', EmploiDuTempsViewSet)

urlpatterns = router.urls
from rest_framework import routers
from .views import EmploiDuTempsViewSet, SalleViewSet

router = routers.DefaultRouter()
router.register(r'emploi-du-temps', EmploiDuTempsViewSet)
router.register(r'salles', SalleViewSet)

urlpatterns = router.urls
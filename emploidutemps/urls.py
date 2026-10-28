from rest_framework import routers
from .views import ActiviteClasseViewSet, EmploiDuTempsViewSet, SalleViewSet

router = routers.DefaultRouter()
router.register(r'emploi-du-temps', EmploiDuTempsViewSet)
router.register(r'salles', SalleViewSet)
router.register(r'activites', ActiviteClasseViewSet, basename='activites')

urlpatterns = router.urls
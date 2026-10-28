from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve
from django.http import JsonResponse
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from smart_back.pagination import StandardResultsSetPagination
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from users.views import MyTokenObtainPairView

def api_home(request):
    return JsonResponse({
        "message": "Bienvenue sur SmartCampus API ",
        
    })

urlpatterns = [
    path('', api_home),  # page d’accueil API

    # ✅ Endpoints JWT
    path('api/auth/login/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),  # alias login
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Admin
    path('admin/', admin.site.urls),

    # Apps
    path('api/auth/', include('users.urls')),
    path("api/v2/", include("academique.urls")),
    path('api/files/', include('files.urls')),
    path('api/admin-api/', include('admin_api.urls')),
    path('api/formateurs/', include('formateurs.urls')),
    path("api/", include("etudiants.urls")),
    path('api/personnels/', include('personnels.urls')),
    path('api/inventaires/', include('inventaires.urls')),
    path("api/", include("paiements.urls")),
    path('api/paie/', include('paie.urls')),
    path('api/', include('logs.urls')),
    path("api/", include("demandes.urls")),
    path('api/conges/', include('conges.urls')),
    path('api/absences/', include('absences.urls')),
    path('api/', include('depenses.urls')),
    path("api/", include("modules.urls")),
    path("api/", include("emploidutemps.urls")),
    path('api/', include('notes.urls')),
    path('api/', include('assiduite.urls')),
    path('api/', include('notifications.urls')),
    path('api/messagerie/', include('messagerie.urls')),
    path('api/', include('attestations.urls')),
    path('api/communication/', include('communication.urls')),
    path("", include("revenus.urls")),

    # OpenAPI schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Fichiers médias (logos, signatures, photos, justificatifs…).
# `static()` ne fait rien quand DEBUG = False : on sert donc /media/ explicitement pour que
# les images restent disponibles en production. (À terme, idéalement servir /media/ via nginx.)
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

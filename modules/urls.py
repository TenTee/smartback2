from django.urls import path
from .views import ModuleListCreateView, ModuleRetrieveUpdateDeleteView

urlpatterns = [
    path("modules/", ModuleListCreateView.as_view(), name="module-list-create"),
    path("modules/<int:pk>/", ModuleRetrieveUpdateDeleteView.as_view(), name="module-detail"),
]
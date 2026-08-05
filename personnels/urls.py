from django.urls import path
from .views import PersonnelListCreateView, PersonnelDetailView

urlpatterns = [
    path('', PersonnelListCreateView.as_view(), name='personnel-list-create'),
    path('<int:pk>/', PersonnelDetailView.as_view(), name='personnel-detail'),
]

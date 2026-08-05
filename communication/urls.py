from django.urls import path
from .views import CommunicationListCreate, CommunicationDetail

urlpatterns = [
    path('', CommunicationListCreate.as_view(), name='communication-list'),
    path('<int:pk>/', CommunicationDetail.as_view(), name='communication-detail'),
]

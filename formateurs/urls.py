# formateurs/urls.py
from django.urls import path
from .views import FormateurListCreateView, FormateurRetrieveUpdateDeleteView

urlpatterns = [
    path('', FormateurListCreateView.as_view(), name='formateur-list'),
    path('<int:pk>/', FormateurRetrieveUpdateDeleteView.as_view(), name='formateur-detail'),
]

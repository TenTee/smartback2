# files/urls.py
from django.urls import path
from .views import FileUploadView, FileListView, FileDeleteView, FileDownloadView

urlpatterns = [
    path('', FileListView.as_view(), name='file-list'),
    path('upload/', FileUploadView.as_view(), name='file-upload'),
    path('<int:pk>/delete/', FileDeleteView.as_view(), name='file-delete'),
    path('<int:pk>/download/', FileDownloadView.as_view(), name='file-download'),
]
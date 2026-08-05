# files/tests.py

import io
import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import File

User = get_user_model()


@pytest.mark.django_db
def test_upload_file():
    client = APIClient()
    # création d'un utilisateur
    user = User.objects.create_user(username='testuser', email='test@test.com', password='pass')
    client.force_authenticate(user=user)

    # fichier simulé
    file_data = SimpleUploadedFile("test.pdf", b"dummy content", content_type="application/pdf")

    response = client.post(
        reverse('file-list-create'),
        {'fichier': file_data, 'type': 'pdf'},
        format='multipart'  # important pour upload
    )
    assert response.status_code == 201
    assert File.objects.filter(uploaded_by=user, type='pdf').exists()


@pytest.mark.django_db
def test_file_download_permission():
    client = APIClient()
    user = User.objects.create_user(username='user1', email='test@test.com', password='pass')
    other_user = User.objects.create_user(username='user2', email='other@test.com', password='pass')

    client.force_authenticate(user=other_user)

    # fichier simulé pour test
    file_data = SimpleUploadedFile("test.pdf", b"dummy content", content_type="application/pdf")
    
    # création du fichier par user1
    file = File.objects.create(
        fichier=file_data,
        uploaded_by=user,
        type='pdf',
        size=file_data.size
    )

    # test que l'autre utilisateur ne peut pas le télécharger
    response = client.get(reverse('file-download', args=[file.id]))
    assert response.status_code == 403


@pytest.mark.django_db
def test_file_owner_can_download():
    client = APIClient()
    user = User.objects.create_user(username='owner', email='owner@test.com', password='pass')
    client.force_authenticate(user=user)

    # fichier simulé
    file_data = SimpleUploadedFile("test.pdf", b"dummy content", content_type="application/pdf")

    # création du fichier
    file = File.objects.create(
        fichier=file_data,
        uploaded_by=user,
        type='pdf',
        size=file_data.size
    )

    # test que le propriétaire peut le télécharger
    response = client.get(reverse('file-download', args=[file.id]))
    assert response.status_code == 200

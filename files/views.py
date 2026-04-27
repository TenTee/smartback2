from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse, Http404
from .models import File
from .serializers import FileSerializer
from users.permissions import HasRolePermission

# --- UPLOAD ---
class FileUploadView(generics.CreateAPIView):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        file_obj = self.request.FILES.get("file")
        if not file_obj:
            raise Http404("Aucun fichier fourni")
        serializer.save(owner=self.request.user)


# --- LIST ---
class FileListView(generics.ListAPIView):
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return File.objects.filter(owner=self.request.user)


# --- DELETE ---
class FileDeleteView(generics.DestroyAPIView):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]
    allowed_roles = ["admin", "finance"]

    def get_queryset(self):
        # ⚠️ Si tu veux que admin/finance puisse supprimer tous les fichiers :
        if self.request.user.role in ["admin", "finance"]:
            return File.objects.all()
        # Sinon, limiter aux fichiers de l’utilisateur
        return File.objects.filter(owner=self.request.user)


# --- DOWNLOAD ---
class FileDownloadView(generics.RetrieveAPIView):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        file_obj = self.get_object()
        # Vérification propriétaire
        if file_obj.owner != request.user and request.user.role not in ["admin", "finance"]:
            raise Http404
        # Local storage
        return FileResponse(file_obj.file.open(), as_attachment=True, filename=file_obj.name)
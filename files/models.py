from django.db import models
from django.conf import settings

class File(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="files",
        null=True, blank=True   # 🔥 Ajouté
    )
    file = models.FileField(
        upload_to="protected_files/",
        null=True, blank=True   # 🔥 Ajouté
    )
    name = models.CharField(max_length=255, default="unknown")
    content_type = models.CharField(
        max_length=100,
        default="application/octet-stream",
        help_text="Type MIME du fichier"
    )
    size = models.PositiveIntegerField(
        null=True, blank=True   # 🔥 Ajouté
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


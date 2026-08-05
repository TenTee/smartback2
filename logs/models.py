from django.db import models


class Log(models.Model):
    horodatage = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=255)      # ex : "backend", "paiement", "auth", "api"
    message = models.TextField()

    def __str__(self):
        return f"[{self.horodatage}] {self.source}"


from django.db import models

class Communication(models.Model):
    titre = models.CharField(max_length=255)
    contenu = models.TextField()   # message / note / annonce interne

    def __str__(self):
        return self.titre

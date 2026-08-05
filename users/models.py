from django.contrib.auth.models import AbstractUser
from django.db import models
import random
import string


class Role(models.Model):
    """
    Rôle fonctionnel avec un code (utilisé par les utilisateurs)
    et permissions à 3 niveaux : aucun / lecture / écriture.
    """
    ACCESS_CHOICES = [
        ('none', 'Aucun'),
        ('lecture', 'Lecture'),
        ('ecriture', 'Écriture'),
    ]

    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=150)

    can_manage_rh = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='none')
    can_manage_pedagogie = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='none')
    can_manage_logistique = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='none')
    can_manage_finance = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='none')
    can_manage_etudiants = models.CharField(max_length=10, choices=ACCESS_CHOICES, default='none')

    def __str__(self):
        return self.libelle


class CustomUser(AbstractUser):
    """
    Utilisateur applicatif lié à un rôle (via son code).
    """

    noms = models.CharField(max_length=150)
    prenoms = models.CharField(max_length=150)
    email = models.EmailField(unique=True)  # ✅ email obligatoire et unique

    # Rôle fonctionnel sous forme de code libre (lié au modèle Role.code)
    role = models.CharField(max_length=50, default="responsableRh")

    username = models.CharField(max_length=150, unique=True, editable=False)
    password = models.CharField(max_length=128, editable=False)

    is_active = models.BooleanField(default=True)  # ✅ désactiver sans supprimer
    date_created = models.DateTimeField(auto_now_add=True)  # ✅ date de création

    def save(self, *args, **kwargs):
        # Génération automatique du username si vide
        if not self.username:
            base_username = f"{self.noms.lower()}.{self.prenoms.lower()}".replace(" ", "")
            suffix = ''.join(random.choices(string.digits, k=3))
            self.username = f"{base_username}{suffix}"

        # Génération automatique du mot de passe si vide
        if not self.password:
            raw_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            self._raw_password = raw_password  # ✅ stock temporaire pour le signal
            self.set_password(raw_password)

        super().save(*args, **kwargs)

    def reset_password(self):
        """Réinitialiser le mot de passe (réservé au superAdmin)."""
        raw_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        self._raw_password = raw_password  # stock temporaire pour le signal
        self.set_password(raw_password)
        self.save()
        return raw_password

    def __str__(self):
        return f"{self.noms} {self.prenoms} ({self.role})"
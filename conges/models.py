from django.db import models


class Conge(models.Model):
    date_debut = models.DateField()
    date_fin = models.DateField()
    type_conge = models.CharField(max_length=50)
    raison = models.TextField(null=True, blank=True)

    statut = models.CharField(
        max_length=20,
        default='en_attente',
        choices=[
            ('en_attente', 'En attente'),
            ('accepte', 'Accepté'),
            ('refuse', 'Refusé'),
        ]
    )

    personnel = models.ForeignKey(
        'personnels.Personnel',
        on_delete=models.CASCADE,
        related_name='conges'
    )

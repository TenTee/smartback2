from rest_framework import serializers
from datetime import time
from .models import EmploiDuTemps

class EmploiDuTempsSerializer(serializers.ModelSerializer):
    formation_nom = serializers.CharField(source="formation.intitule", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    formateur_nom = serializers.CharField(source="formateur.nom", read_only=True)

    class Meta:
        model = EmploiDuTemps
        fields = "__all__"

    def validate(self, data):
        """Validation métier côté API (renvoie 400 au lieu de 500)."""

        # 1️⃣ Bloquer la pause commune
        pause_debut = time(12, 0)
        pause_fin = time(13, 0)
        if data["heure_debut"] < pause_fin and data["heure_fin"] > pause_debut:
            raise serializers.ValidationError({
                "non_field_errors": ["⏸️ Impossible de programmer une séance pendant la pause déjeuner (12h00–13h00)."]
            })

        # 2️⃣ Empêcher conflits de salle (hors tronc communs du même module)
        conflits_salle = EmploiDuTemps.objects.filter(
            jour=data["jour"],
            salle=data["salle"],
            heure_debut__lt=data["heure_fin"],
            heure_fin__gt=data["heure_debut"]
        ).exclude(module=data["module"])  # ✅ ignore duplications du même module

        if self.instance and self.instance.pk:
            conflits_salle = conflits_salle.exclude(pk=self.instance.pk)

        if conflits_salle.exists():
            raise serializers.ValidationError({
                "non_field_errors": ["⚠️ Conflit de salle : cette salle est déjà occupée à ce créneau."]
            })

        # 3️⃣ Empêcher conflits globaux (hors tronc communs du même module)
        conflits_horaire = EmploiDuTemps.objects.filter(
            jour=data["jour"],
            heure_debut__lt=data["heure_fin"],
            heure_fin__gt=data["heure_debut"]
        ).exclude(module=data["module"])  # ✅ ignore duplications du même module

        if self.instance and self.instance.pk:
            conflits_horaire = conflits_horaire.exclude(pk=self.instance.pk)

        if conflits_horaire.exists():
            raise serializers.ValidationError({
                "non_field_errors": ["⚠️ Conflit détecté : une autre séance est déjà programmée à ce créneau."]
            })

        return data

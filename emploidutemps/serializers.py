from rest_framework import serializers
from datetime import time
from .models import EmploiDuTemps, Salle
from academique.models import Filiere, Niveau

class SalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Salle
        fields = "__all__"

class EmploiDuTempsSerializer(serializers.ModelSerializer):
    filiere_nom = serializers.CharField(source="filiere.nom", read_only=True)
    niveau_nom = serializers.CharField(source="niveau.nom", read_only=True)
    classe_nom = serializers.CharField(source="classe.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    formateur_nom = serializers.CharField(source="formateur.nom", read_only=True)
    salle_nom = serializers.CharField(source="salle.nom", read_only=True)

    filiere = serializers.PrimaryKeyRelatedField(queryset=Filiere.objects.all(), required=False, allow_null=True)
    niveau = serializers.PrimaryKeyRelatedField(queryset=Niveau.objects.all(), required=False, allow_null=True)
    salle = serializers.PrimaryKeyRelatedField(queryset=Salle.objects.all())

    class Meta:
        model = EmploiDuTemps
        fields = "__all__"

    def validate(self, data):
        """Validation métier côté API (renvoie 400 au lieu de 500)."""

        # 1️⃣ Bloquer la pause par cycle
        classe = data.get("classe")
        if classe and classe.cycle and classe.cycle.type_cycle:
            cg = classe.cycle.type_cycle
            pause_debut = cg.heure_pause_debut
            pause_fin = cg.heure_pause_fin
            
            if data["heure_debut"] < pause_fin and data["heure_fin"] > pause_debut:
                raise serializers.ValidationError({
                    "non_field_errors": [f"⏸️ Impossible de programmer une séance pendant la pause ({pause_debut.strftime('%H:%M')}–{pause_fin.strftime('%H:%M')})."]
                })
        else:
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

        # 3️⃣ Empêcher conflits de classe (même classe, même créneau)
        classe = data.get("classe")
        if classe:
            conflits_classe = EmploiDuTemps.objects.filter(
                jour=data["jour"],
                classe=classe,
                heure_debut__lt=data["heure_fin"],
                heure_fin__gt=data["heure_debut"]
            ).exclude(module=data["module"])

            if self.instance and self.instance.pk:
                conflits_classe = conflits_classe.exclude(pk=self.instance.pk)

            if conflits_classe.exists():
                raise serializers.ValidationError({
                    "non_field_errors": ["⚠️ Conflit de classe : cette classe a déjà un cours à ce créneau."]
                })

        # 4️⃣ Empêcher conflits de formateur (même formateur, même créneau)
        formateur = data.get("formateur")
        if formateur:
            conflits_formateur = EmploiDuTemps.objects.filter(
                jour=data["jour"],
                formateur=formateur,
                heure_debut__lt=data["heure_fin"],
                heure_fin__gt=data["heure_debut"]
            ).exclude(module=data["module"])

            if self.instance and self.instance.pk:
                conflits_formateur = conflits_formateur.exclude(pk=self.instance.pk)

            if conflits_formateur.exists():
                raise serializers.ValidationError({
                    "non_field_errors": ["⚠️ Conflit de formateur : ce formateur a déjà un cours à ce créneau."]
                })

        return data

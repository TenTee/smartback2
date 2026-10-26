from rest_framework import serializers
from datetime import time
from .models import EmploiDuTemps, Salle, periode_q
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

    # Tronc commun
    tronc_commun = serializers.UUIDField(read_only=True)
    tronc_commun_classes = serializers.SerializerMethodField()
    classes_tronc_commun = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False, allow_null=True,
        help_text="Classes du tronc commun (création / modification). Liste vide = retirer les autres classes.",
    )

    class Meta:
        model = EmploiDuTemps
        fields = "__all__"

    def get_tronc_commun_classes(self, obj):
        """Autres classes suivant ce cours en tronc commun (même créneau)."""
        if not obj.tronc_commun:
            return []
        cache = self.context.setdefault("_tronc_commun", {})
        if obj.tronc_commun not in cache:
            cache[obj.tronc_commun] = list(
                EmploiDuTemps.objects.filter(tronc_commun=obj.tronc_commun)
                .select_related("classe").values("id", "classe_id", "classe__nom")
            )
        return [
            {"emploi_id": m["id"], "classe_id": m["classe_id"], "classe_nom": m["classe__nom"]}
            for m in cache[obj.tronc_commun] if m["id"] != obj.id
        ]

    def _hors_groupe(self, qs):
        """Ignore ce créneau, les autres classes de son tronc commun et les créneaux qui vont y être rattachés."""
        inst = self.instance
        if inst is not None and inst.pk:
            qs = qs.exclude(pk=inst.pk)
            if inst.tronc_commun:
                qs = qs.exclude(tronc_commun=inst.tronc_commun)
        a_rattacher = getattr(self, "_a_rattacher", None)
        if a_rattacher is not None:
            qs = qs.exclude(pk__in=a_rattacher)
        return qs

    def validate(self, data):
        """Validation métier côté API (renvoie 400 au lieu de 500)."""
        # Valeurs effectives (création ou mise à jour partielle)
        inst = self.instance
        for key in ("jour", "heure_debut", "heure_fin", "salle", "module"):
            if key not in data and inst is not None:
                data[key] = getattr(inst, key)
        date_debut = data.get("date_debut", getattr(inst, "date_debut", None) if inst else None)
        date_fin = data.get("date_fin", getattr(inst, "date_fin", None) if inst else None)
        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({"date_fin": ["La date de fin de période doit être postérieure à la date de début."]})
        if data["heure_fin"] <= data["heure_debut"]:
            raise serializers.ValidationError({"heure_fin": ["L'heure de fin doit être après l'heure de début."]})
        periode = periode_q(date_debut, date_fin)

        # Classes du tronc commun déjà programmées séparément sur ce même cours / créneau : rattachées, pas en conflit
        self._a_rattacher = None
        if data.get("classes_tronc_commun"):
            from .tronc_commun import adoptables
            self._a_rattacher = list(adoptables(
                data["module"].pk, data["classes_tronc_commun"], data["jour"], data["heure_debut"], data["heure_fin"],
                date_debut, date_fin, sauf_pk=getattr(inst, "pk", None),
            ).values_list("pk", flat=True))

        # 1️⃣ Pause de la classe (ou du cycle)
        from .horaires import erreur_horaires
        erreur = erreur_horaires(data.get("classe") or getattr(inst, "classe", None), data["heure_debut"], data["heure_fin"], verifier_journee=False)
        if erreur:
            raise serializers.ValidationError({"non_field_errors": [erreur]})

        # 2️⃣ Empêcher conflits de salle (hors tronc communs du même module)
        conflits_salle = EmploiDuTemps.objects.filter(periode).filter(
            jour=data["jour"],
            salle=data["salle"],
            heure_debut__lt=data["heure_fin"],
            heure_fin__gt=data["heure_debut"]
        )
        conflits_salle = self._hors_groupe(conflits_salle)

        if conflits_salle.exists():
            raise serializers.ValidationError({
                "non_field_errors": ["⚠️ Conflit de salle : cette salle est déjà occupée à ce créneau."]
            })

        # 3️⃣ Empêcher conflits de classe (même classe, même créneau)
        classe = data.get("classe")
        if classe:
            conflits_classe = EmploiDuTemps.objects.filter(periode).filter(
                jour=data["jour"],
                classe=classe,
                heure_debut__lt=data["heure_fin"],
                heure_fin__gt=data["heure_debut"]
            )

            if self.instance and self.instance.pk:
                conflits_classe = conflits_classe.exclude(pk=self.instance.pk)

            if conflits_classe.exists():
                raise serializers.ValidationError({
                    "non_field_errors": ["⚠️ Conflit de classe : cette classe a déjà un cours à ce créneau."]
                })

        # 4️⃣ Empêcher conflits de formateur (même formateur, même créneau)
        formateur = data.get("formateur")
        if formateur:
            conflits_formateur = EmploiDuTemps.objects.filter(periode).filter(
                jour=data["jour"],
                formateur=formateur,
                heure_debut__lt=data["heure_fin"],
                heure_fin__gt=data["heure_debut"]
            )
            conflits_formateur = self._hors_groupe(conflits_formateur)

            if conflits_formateur.exists():
                raise serializers.ValidationError({
                    "non_field_errors": ["⚠️ Conflit de formateur : ce formateur a déjà un cours à ce créneau."]
                })

        return data

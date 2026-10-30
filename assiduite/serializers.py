from rest_framework import serializers
from .models import AssiduiteRecord


class AssiduiteRecordSerializer(serializers.ModelSerializer):
    etudiant_nom = serializers.CharField(source="etudiant.nom", read_only=True)
    etudiant_matricule = serializers.CharField(source="etudiant.matricule", read_only=True)
    filiere_nom = serializers.CharField(source="etudiant.filiere.nom", read_only=True)
    module_nom = serializers.CharField(source="module.nom", read_only=True)
    parent_nom = serializers.CharField(source="etudiant.nom_parent", read_only=True)
    parent_whatsapp = serializers.CharField(source="etudiant.whatsapp_parent", read_only=True)
    formateur_nom = serializers.CharField(source="emploi.formateur.nom", read_only=True, default="")
    classe_nom = serializers.CharField(source="emploi.classe.nom", read_only=True, default="")

    class Meta:
        model = AssiduiteRecord
        fields = [
            "id",
            "etudiant",
            "etudiant_nom",
            "etudiant_matricule",
            "filiere_nom",
            "module",
            "module_nom",
            "emploi",
            "heure_debut",
            "heure_fin",
            "formateur_nom",
            "classe_nom",
            "date",
            "type",
            "minutes_retard",
            "justifie",
            "justificatif",
            "justificatif_texte",
            "parent_nom",
            "parent_whatsapp",
            "created_at",
        ]
        read_only_fields = ["heure_debut", "heure_fin"]
        extra_kwargs = {"module": {"required": False}}

    def validate(self, attrs):
        type_value = attrs.get("type") or (self.instance.type if self.instance else None)
        minutes = attrs.get("minutes_retard")
        justifie = attrs.get("justifie", self.instance.justifie if self.instance else False)
        justificatif = attrs.get("justificatif", self.instance.justificatif if self.instance else None)
        texte = attrs.get("justificatif_texte", self.instance.justificatif_texte if self.instance else "")

        if type_value == "RETARD":
            if minutes is None:
                raise serializers.ValidationError({"minutes_retard": "Les minutes de retard sont requises."})
        if type_value == "ABSENCE":
            attrs["minutes_retard"] = None
        
        if justifie and not justificatif and not (texte or "").strip():
            raise serializers.ValidationError({"justificatif": "Joignez un fichier ou écrivez la justification de l'absence ou du retard."})

        # Le cours est fixé par l'emploi du temps : l'absence / le retard porte sur une séance du jour
        from academique.middleware import get_current_academic_year_id
        from .seances_jour import seances_du_jour
        etudiant = attrs.get("etudiant") or (self.instance.etudiant if self.instance else None)
        jour = attrs.get("date") or (self.instance.date if self.instance else None)
        emploi = attrs.get("emploi") if "emploi" in attrs else (self.instance.emploi if self.instance else None)
        verifier = self.instance is None or any(k in attrs for k in ("emploi", "date", "etudiant"))
        if etudiant and jour and verifier:
            classe, seances = seances_du_jour(etudiant, jour, get_current_academic_year_id())
            if emploi is None:
                if self.instance is None or "emploi" in attrs:
                    if not seances:
                        raise serializers.ValidationError({"emploi": f"Aucun cours n'est programmé le {jour.strftime('%d-%m-%Y')} pour la classe de l'étudiant{f' ({classe.nom})' if classe else ''} dans l'emploi du temps."})
                    raise serializers.ValidationError({"emploi": "Choisissez la séance du jour concernée."})
            else:
                if emploi.id not in {e.id for e in seances}:
                    raise serializers.ValidationError({"emploi": "Cette séance n'a pas lieu ce jour-là pour la classe de l'étudiant."})
                attrs["module"] = emploi.module
                attrs["heure_debut"] = emploi.heure_debut
                attrs["heure_fin"] = emploi.heure_fin
                doublon = AssiduiteRecord.objects.filter(etudiant=etudiant, emploi=emploi, date=jour)
                if self.instance:
                    doublon = doublon.exclude(pk=self.instance.pk)
                if doublon.exists():
                    raise serializers.ValidationError({"emploi": f"Une absence / un retard est déjà enregistré pour cette séance ({emploi.module.nom})."})
                if type_value == "RETARD" and minutes is not None:
                    duree = (emploi.heure_fin.hour * 60 + emploi.heure_fin.minute) - (emploi.heure_debut.hour * 60 + emploi.heure_debut.minute)
                    if minutes > duree:
                        raise serializers.ValidationError({"minutes_retard": f"Le retard ne peut pas dépasser la durée de la séance ({duree} min)."})
        if not attrs.get("module") and not (self.instance and self.instance.module_id):
            raise serializers.ValidationError({"emploi": "Choisissez la séance du jour concernée."})

        return attrs

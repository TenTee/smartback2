import os

from rest_framework import serializers

from personnels.models import Personnel
from personnels.serializers import PersonnelSerializer

from .models import DemandeAbsence

ALLOWED_PREUVE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_PREUVE_SIZE = 10 * 1024 * 1024


class DemandeAbsenceSerializer(serializers.ModelSerializer):
    personnel_id = serializers.PrimaryKeyRelatedField(
        queryset=Personnel.objects.all(),
        source="personnel",
        write_only=True,
    )
    personnel = PersonnelSerializer(read_only=True)

    class Meta:
        model = DemandeAbsence
        fields = [
            "id",
            "personnel",
            "personnel_id",
            "motif",
            "date",
            "preuve",
            "statut",
            "date_demande",
        ]
        read_only_fields = ["date_demande"]

    def validate_preuve(self, file):
        if file is None:
            return file
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in ALLOWED_PREUVE_EXTENSIONS:
            raise serializers.ValidationError(
                "La preuve doit être un fichier PDF ou une image (jpg, jpeg, png, webp, gif)."
            )
        if file.size > MAX_PREUVE_SIZE:
            raise serializers.ValidationError("La preuve ne doit pas dépasser 10 Mo.")
        return file

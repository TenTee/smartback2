# files/serializers.py
from rest_framework import serializers
from .models import File

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ["id", "name", "file", "content_type", "size", "created_at"]
        read_only_fields = ["name", "content_type", "size", "created_at"]


    def validate_file(self, value):
        # Vérification taille (ex: max 5 Mo)
        max_size = 5 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("Le fichier dépasse la taille maximale de 5 Mo.")

        # Vérification type MIME
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Type de fichier non autorisé.")
        return value

    def create(self, validated_data):
        uploaded_file = validated_data["file"]
        validated_data["name"] = uploaded_file.name
        validated_data["size"] = uploaded_file.size
        validated_data["content_type"] = getattr(uploaded_file, "content_type", "application/octet-stream")
        return super().create(validated_data)


from rest_framework import serializers
from .models import Log

class LogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Log
        fields = ['id', 'horodatage', 'source', 'message']
        read_only_fields = ['id', 'horodatage']  # horodatage généré automatiquement

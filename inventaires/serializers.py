from rest_framework import serializers
from .models import Inventaire

class InventaireSerializer(serializers.ModelSerializer):
    quantite = serializers.IntegerField(write_only=True, required=False, default=1)

    class Meta:
        model = Inventaire
        fields = '__all__'
        read_only_fields = ['reference']

    def create(self, validated_data):
        quantite = validated_data.pop('quantite', 1)
        articles = []
        for i in range(quantite):
            article = Inventaire.objects.create(**validated_data)
            articles.append(article)
        return articles if quantite > 1 else articles[0]
from rest_framework import serializers
from .models import Module
from academique.models import Filiere, Cycle, Niveau, CourseAssignment

class ModuleSerializer(serializers.ModelSerializer):
    formateurs = serializers.SerializerMethodField()
    attributions = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            'id', 'nom', 'duree', 'coefficient',
            'semestre',
            'formateurs', 'attributions'
        ]

    def get_formateurs(self, obj):
        return [
            {
                "id": f.id,
                "nom": f.nom,
                "email": f.email,
                "contact": f.contact
            }
            for f in obj.formateurs.all()
        ]

    def get_attributions(self, obj):
        assignments = CourseAssignment.objects.filter(module=obj).select_related('filiere', 'cycle', 'niveau')
        return [
            {
                "id": ass.id,
                "filiere_nom": ass.filiere.nom,
                "cycle_nom": ass.cycle.nom,
                "niveau_nom": ass.niveau.nom,
            }
            for ass in assignments
        ]

from rest_framework import serializers
from .models import Module
from academique.models import Filiere, Cycle, Niveau, CourseAssignment

class ModuleSerializer(serializers.ModelSerializer):
    formateurs = serializers.SerializerMethodField()
    attributions = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            'id', 'nom', 'description', 'duree', 'coefficient',
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
        # 1. Attributions via CourseAssignment
        assignments = CourseAssignment.objects.filter(module=obj).select_related('filiere', 'cycle', 'niveau')
        res = [
            {
                "id": ass.id,
                "filiere_id": ass.filiere_id,
                "filiere_nom": ass.filiere.nom,
                "cycle_id": ass.cycle_id,
                "cycle_nom": ass.cycle.nom,
                "niveau_id": ass.niveau_id,
                "niveau_nom": ass.niveau.nom,
            }
            for ass in assignments
        ]
        # 2. Liaisons directes avec les classes
        for cls in obj.classes_academique.select_related('filiere', 'niveau'):
            res.append({
                "id": f"cls-{cls.id}",
                "classe_id": cls.id,
                "classe_nom": cls.nom,
                "filiere_id": cls.filiere_id,
                "filiere_nom": cls.filiere.nom if cls.filiere else "",
                "niveau_id": cls.niveau_id,
                "niveau_nom": cls.niveau.nom if cls.niveau else "",
            })
        return res

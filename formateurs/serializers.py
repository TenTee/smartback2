# formateurs/serializers.py
from rest_framework import serializers
from .models import Formateur, CoursDocument


class FormateurSerializer(serializers.ModelSerializer):
    specialites_nom = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()

    class Meta:
        model = Formateur
        fields = [
            'id',
            'nom',
            'email',
            'contact',
            'type_formateur',
            'salaire',
            'taux_horaire',
            'specialites',
            'specialites_nom',
            'user',
            'username',
        ]

    def get_specialites_nom(self, obj):
        return [m.nom for m in obj.specialites.all()]

    def get_username(self, obj):
        if obj.user:
            return obj.user.username
        return None


class FormateurPortalSerializer(serializers.ModelSerializer):
    specialites_nom = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True)
    classes = serializers.SerializerMethodField()

    class Meta:
        model = Formateur
        fields = [
            'id',
            'nom',
            'email',
            'contact',
            'type_formateur',
            'specialites_nom',
            'username',
            'classes',
        ]

    def get_specialites_nom(self, obj):
        return [m.nom for m in obj.specialites.all()]

    def get_classes(self, obj):
        from academique.models import Affectation
        from emploidutemps.models import EmploiDuTemps
        from academique.middleware import get_current_academic_year_id

        annee_id = get_current_academic_year_id()
        seen = set()
        result = []

        aff_qs = Affectation.objects.filter(enseignant=obj)
        if annee_id:
            aff_qs = aff_qs.filter(classe__annee_academique_id=annee_id)
        for a in aff_qs.select_related('classe', 'module'):
            key = (a.classe.id, a.module.id)
            if key not in seen:
                seen.add(key)
                result.append({
                    'id': a.classe.id,
                    'nom': str(a.classe),
                    'module_id': a.module.id,
                    'module_nom': a.module.nom,
                })

        edt_qs = EmploiDuTemps.objects.filter(formateur=obj)
        if annee_id:
            edt_qs = edt_qs.filter(classe__annee_academique_id=annee_id)
        for edt in edt_qs.select_related('classe', 'module'):
            if edt.classe and edt.module:
                key = (edt.classe.id, edt.module.id)
                if key not in seen:
                    seen.add(key)
                    result.append({
                        'id': edt.classe.id,
                        'nom': str(edt.classe),
                        'module_id': edt.module.id,
                        'module_nom': edt.module.nom,
                    })

        return result


class CoursDocumentSerializer(serializers.ModelSerializer):
    module_nom = serializers.CharField(source='module.nom', read_only=True)
    fichier_url = serializers.SerializerMethodField()

    class Meta:
        model = CoursDocument
        fields = [
            'id',
            'formateur',
            'module',
            'module_nom',
            'titre',
            'description',
            'fichier',
            'fichier_url',
            'est_visible_etudiants',
            'date_upload',
        ]
        read_only_fields = ['formateur', 'date_upload']

    def get_fichier_url(self, obj):
        request = self.context.get('request')
        if obj.fichier and request:
            return request.build_absolute_uri(obj.fichier.url)
        return None

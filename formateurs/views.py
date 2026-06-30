# formateurs/views.py
from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from .models import Formateur, CoursDocument
from .serializers import FormateurSerializer, FormateurPortalSerializer, CoursDocumentSerializer


class FormateurListCreateView(generics.ListCreateAPIView):
    queryset = Formateur.objects.all()
    serializer_class = FormateurSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["specialites"]

    def perform_create(self, serializer):
        from users.models import CustomUser
        from django.utils.crypto import get_random_string

        formateur = serializer.save()

        if not formateur.user:
            nom_parts = formateur.nom.lower().replace(" ", "").split()
            base_username = ".".join(nom_parts) if nom_parts else "formateur"
            suffix = get_random_string(3, allowed_chars='0123456789')
            username = f"{base_username}{suffix}"

            raw_password = get_random_string(8)
            user = CustomUser(
                noms=formateur.nom,
                prenoms='',
                email=formateur.email,
                username=username,
                role='formateur',
            )
            user.set_password(raw_password)
            user.save()

            formateur.user = user
            formateur.save(update_fields=['user'])

            formateur._generated_username = username
            formateur._generated_password = raw_password

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        data = serializer.data
        formateur = serializer.instance
        if hasattr(formateur, '_generated_username'):
            data['credentials'] = {
                'username': formateur._generated_username,
                'password': formateur._generated_password,
            }

        return Response(data, status=status.HTTP_201_CREATED)


class FormateurRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Formateur.objects.all()
    serializer_class = FormateurSerializer


class FormateurGenerateAccountView(generics.GenericAPIView):
    queryset = Formateur.objects.all()
    permission_classes = [IsAuthenticated]

    def post(self, request, pk=None):
        from users.models import CustomUser
        from django.utils.crypto import get_random_string

        formateur = self.get_object()
        if formateur.user:
            return Response(
                {'detail': 'Ce formateur a deja un compte.', 'username': formateur.user.username},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nom_parts = formateur.nom.lower().replace(" ", "").split()
        base_username = ".".join(nom_parts) if nom_parts else "formateur"
        suffix = get_random_string(3, allowed_chars='0123456789')
        username = f"{base_username}{suffix}"
        raw_password = get_random_string(8)

        user = CustomUser(
            noms=formateur.nom,
            prenoms='',
            email=formateur.email,
            username=username,
            role='formateur',
        )
        user.set_password(raw_password)
        user.save()

        formateur.user = user
        formateur.save(update_fields=['user'])

        return Response({
            'username': username,
            'password': raw_password,
        })


class FormateurPortalViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _get_formateur(self, request):
        if not hasattr(request.user, 'formateur_profile'):
            return None
        return request.user.formateur_profile

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response(
                {"detail": "Profil formateur introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = FormateurPortalSerializer(formateur, context={'request': request})
        return Response(serializer.data)

    def _get_classe_module_pairs(self, formateur):
        from academique.models import Affectation
        from emploidutemps.models import EmploiDuTemps

        pairs = set()

        for aff in Affectation.objects.filter(enseignant=formateur).select_related('classe', 'module'):
            pairs.add((aff.classe, aff.module))

        for edt in EmploiDuTemps.objects.filter(formateur=formateur).select_related('classe', 'module'):
            if edt.classe and edt.module:
                pairs.add((edt.classe, edt.module))

        return list(pairs)

    @action(detail=False, methods=['get'], url_path='mes-classes')
    def mes_classes(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from etudiants.models import Inscription
        from academique.middleware import get_current_academic_year_id

        annee_id = get_current_academic_year_id()
        pairs = self._get_classe_module_pairs(formateur)

        result = []
        for classe, module in pairs:
            inscriptions = Inscription.objects.filter(classe=classe)
            if annee_id:
                inscriptions = inscriptions.filter(annee_academique_id=annee_id)

            etudiants = []
            for insc in inscriptions.select_related('etudiant'):
                et = insc.etudiant
                etudiants.append({
                    'id': et.id,
                    'matricule': et.matricule,
                    'nom': et.nom,
                    'email': getattr(et, 'email', ''),
                })

            result.append({
                'classe_id': classe.id,
                'classe_nom': str(classe),
                'module_id': module.id,
                'module_nom': module.nom,
                'effectif': len(etudiants),
                'etudiants': etudiants,
            })

        return Response(result)

    @action(detail=False, methods=['get'], url_path='mon-emploi-du-temps')
    def mon_emploi_du_temps(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from emploidutemps.models import EmploiDuTemps
        from emploidutemps.serializers import EmploiDuTempsSerializer

        schedules = EmploiDuTemps.objects.filter(formateur=formateur)
        serializer = EmploiDuTempsSerializer(schedules, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='mes-notes')
    def mes_notes(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from notes.models import Note

        module_id = request.query_params.get('module_id')
        classe_id = request.query_params.get('classe_id')

        pairs = self._get_classe_module_pairs(formateur)
        module_ids = set(m.id for _, m in pairs)
        classe_ids = set(c.id for c, _ in pairs)

        if module_id:
            module_ids = {int(module_id)} & module_ids
        if classe_id:
            classe_ids = {int(classe_id)} & classe_ids

        notes = Note.objects.filter(
            module_id__in=module_ids,
            classe_id__in=classe_ids,
        ).select_related('etudiant', 'module', 'classe', 'evaluation')

        data = []
        for note in notes:
            data.append({
                'id': note.id,
                'etudiant_id': note.etudiant.id,
                'etudiant_nom': note.etudiant.nom,
                'etudiant_matricule': note.etudiant.matricule,
                'module_id': note.module.id,
                'module_nom': note.module.nom,
                'classe_id': note.classe.id if note.classe else None,
                'classe_nom': str(note.classe) if note.classe else '',
                'evaluation_id': note.evaluation.id if note.evaluation else None,
                'note_cc': float(note.note_cc) if note.note_cc else None,
                'note_sn': float(note.note_sn) if note.note_sn else None,
                'note_rattrapage': float(note.note_rattrapage) if note.note_rattrapage else None,
                'note_finale': float(note.note_finale) if note.note_finale else None,
            })

        return Response(data)

    @action(detail=False, methods=['post'], url_path='saisir-notes')
    def saisir_notes(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from notes.models import Note

        notes_data = request.data.get('notes', [])
        if not notes_data:
            return Response({"detail": "Aucune note fournie."}, status=400)

        pairs = self._get_classe_module_pairs(formateur)
        allowed_module_ids = set(m.id for _, m in pairs)

        created_count = 0
        updated_count = 0
        errors = []

        for item in notes_data:
            module_id = item.get('module_id')
            if module_id and int(module_id) not in allowed_module_ids:
                errors.append(f"Module {module_id} non autorise pour ce formateur.")
                continue

            try:
                note, created = Note.objects.update_or_create(
                    etudiant_id=item['etudiant_id'],
                    module_id=item['module_id'],
                    classe_id=item.get('classe_id'),
                    evaluation_id=item.get('evaluation_id'),
                    defaults={
                        'note_cc': item.get('note_cc'),
                        'note_sn': item.get('note_sn'),
                        'note_rattrapage': item.get('note_rattrapage'),
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            except Exception as e:
                errors.append(str(e))

        return Response({
            'created': created_count,
            'updated': updated_count,
            'errors': errors,
        })

    @action(detail=False, methods=['get'], url_path='mon-suivi')
    def mon_suivi(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from emploidutemps.models import EmploiDuTemps
        from notes.models import Note

        total_cours = EmploiDuTemps.objects.filter(formateur=formateur).count()
        pairs = self._get_classe_module_pairs(formateur)

        module_ids = set(m.id for _, m in pairs)
        classe_ids = set(c.id for c, _ in pairs)

        total_notes_saisies = Note.objects.filter(
            module_id__in=module_ids,
            classe_id__in=classe_ids,
        ).count()

        return Response({
            'total_seances_semaine': total_cours,
            'total_classes': len(pairs),
            'total_modules': len(module_ids),
            'total_notes_saisies': total_notes_saisies,
        })

    @action(detail=False, methods=['get'], url_path='mes-epreuves')
    def mes_epreuves(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from academique.models import Epreuve

        epreuves = Epreuve.objects.filter(auteur=formateur.nom)
        data = []
        for ep in epreuves:
            data.append({
                'id': ep.id,
                'nom': ep.nom,
                'module_nom': ep.module.nom if ep.module else '',
                'filiere_nom': ep.filiere.nom if ep.filiere else '',
                'niveau_nom': str(ep.niveau) if ep.niveau else '',
                'type_epreuve': ep.type_epreuve,
                'semestre': str(ep.semestre) if ep.semestre else '',
                'est_partage': ep.est_partage,
                'fichier': ep.fichier.url if ep.fichier else None,
                'corrige': ep.corrige.url if ep.corrige else None,
                'date_creation': ep.date_creation if hasattr(ep, 'date_creation') else None,
            })

        return Response(data)

    @action(detail=False, methods=['post'], url_path='upload-epreuve')
    def upload_epreuve(self, request):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from academique.models import Epreuve

        fichier = request.FILES.get('fichier')
        corrige = request.FILES.get('corrige')
        if not fichier:
            return Response({"detail": "Le fichier sujet est obligatoire."}, status=400)

        module_id = request.data.get('module_id')
        if not module_id:
            return Response({"detail": "Le module est obligatoire."}, status=400)

        filiere_id = request.data.get('filiere_id')
        niveau_id = request.data.get('niveau_id')
        annee_academique_id = request.data.get('annee_academique_id')

        if not filiere_id or not niveau_id or not annee_academique_id:
            pairs = self._get_classe_module_pairs(formateur)
            for classe, module in pairs:
                if module.id == int(module_id):
                    if not filiere_id:
                        filiere_id = classe.filiere_id
                    if not niveau_id:
                        niveau_id = classe.niveau_id
                    if not annee_academique_id:
                        annee_academique_id = classe.annee_academique_id
                    break

        if not filiere_id or not niveau_id or not annee_academique_id:
            return Response({"detail": "Impossible de determiner filiere/niveau/annee."}, status=400)

        epreuve = Epreuve.objects.create(
            nom=request.data.get('nom', ''),
            module_id=module_id,
            filiere_id=filiere_id,
            niveau_id=niveau_id,
            annee_academique_id=annee_academique_id,
            semestre_id=request.data.get('semestre_id') or None,
            type_epreuve=request.data.get('type_epreuve', 'EXAMEN'),
            auteur=formateur.nom,
            est_partage=request.data.get('est_partage', 'false').lower() == 'true',
            fichier=fichier,
            corrige=corrige,
        )

        return Response({
            'id': epreuve.id,
            'nom': epreuve.nom,
            'est_partage': epreuve.est_partage,
        }, status=201)

    @action(detail=False, methods=['patch'], url_path='toggle-partage-epreuve/(?P<epreuve_id>[0-9]+)')
    def toggle_partage_epreuve(self, request, epreuve_id=None):
        formateur = self._get_formateur(request)
        if not formateur:
            return Response({"detail": "Profil formateur introuvable."}, status=404)

        from academique.models import Epreuve

        try:
            epreuve = Epreuve.objects.get(id=epreuve_id, auteur=formateur.nom)
        except Epreuve.DoesNotExist:
            return Response({"detail": "Épreuve introuvable."}, status=404)

        epreuve.est_partage = not epreuve.est_partage
        epreuve.save()
        return Response({'id': epreuve.id, 'est_partage': epreuve.est_partage})


class CoursDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = CoursDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'formateur_profile'):
            return CoursDocument.objects.filter(formateur=user.formateur_profile)
        return CoursDocument.objects.none()

    def perform_create(self, serializer):
        serializer.save(formateur=self.request.user.formateur_profile)

    @action(detail=True, methods=['patch'], url_path='toggle-visibilite')
    def toggle_visibilite(self, request, pk=None):
        doc = self.get_object()
        doc.est_visible_etudiants = not doc.est_visible_etudiants
        doc.save()
        return Response({'id': doc.id, 'est_visible_etudiants': doc.est_visible_etudiants})


class CoursDocumentEtudiantView(generics.ListAPIView):
    serializer_class = CoursDocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CoursDocument.objects.filter(est_visible_etudiants=True)

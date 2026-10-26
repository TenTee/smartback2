from rest_framework import viewsets, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from .models import EmploiDuTemps, Salle, SeanceRealisee, periode_q, semaine_de
from .serializers import EmploiDuTempsSerializer, SalleSerializer

class SalleViewSet(viewsets.ModelViewSet):
    queryset = Salle.objects.all()
    serializer_class = SalleSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nom", "description"]
    ordering_fields = ["nom"]

class EmploiDuTempsViewSet(viewsets.ModelViewSet):
    queryset = EmploiDuTemps.objects.all()
    serializer_class = EmploiDuTempsSerializer

    # 🔎 Ajout de filtres et recherche
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["jour", "filiere", "niveau", "classe", "formateur", "module", "salle"]
    search_fields = ["salle__nom", "filiere__nom", "formateur__nom", "module__nom"]
    ordering_fields = ["heure_debut", "heure_fin"]

    @staticmethod
    def _parse_date(value):
        from django.utils.dateparse import parse_date
        try:
            return parse_date(value) if value else None
        except (TypeError, ValueError):
            return None

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        # ?date_debut=YYYY-MM-DD&date_fin=YYYY-MM-DD → créneaux de cette période (+ permanents)
        # ?date=YYYY-MM-DD → créneaux de la semaine contenant cette date
        date_debut = self._parse_date(params.get("date_debut"))
        date_fin = self._parse_date(params.get("date_fin"))
        jour = self._parse_date(params.get("date"))
        if jour and not (date_debut or date_fin):
            date_debut, date_fin = semaine_de(jour)
        if self.action == "list" and (date_debut or date_fin):
            queryset = queryset.filter(periode_q(date_debut, date_fin))
        return queryset

    @action(detail=False, methods=["post"], url_path="dupliquer")
    def dupliquer(self, request):
        """
        Copie les créneaux d'une période vers une autre (ex. semaine suivante).
        Corps : source_debut, source_fin, cible_debut, cible_fin, classe (optionnel), remplacer (bool).
        """
        from django.db import transaction
        data = request.data
        source_debut = self._parse_date(data.get("source_debut"))
        source_fin = self._parse_date(data.get("source_fin"))
        cible_debut = self._parse_date(data.get("cible_debut"))
        cible_fin = self._parse_date(data.get("cible_fin"))
        if not (source_debut and source_fin and cible_debut and cible_fin):
            return Response({"error": "Les périodes source et cible sont requises (YYYY-MM-DD)."}, status=400)
        if cible_fin < cible_debut:
            return Response({"error": "La période cible est invalide."}, status=400)

        source = EmploiDuTemps.objects.filter(date_debut=source_debut, date_fin=source_fin)
        cible = EmploiDuTemps.objects.filter(date_debut=cible_debut, date_fin=cible_fin)
        classe_id = data.get("classe")
        if classe_id:
            source = source.filter(classe_id=classe_id)
            cible = cible.filter(classe_id=classe_id)
        if not source.exists():
            return Response({"error": "Aucun créneau à copier sur la période source."}, status=400)

        crees, erreurs = 0, []
        with transaction.atomic():
            if str(data.get("remplacer", "")).lower() in ("1", "true", "yes", "oui"):
                for old in cible:
                    super(EmploiDuTemps, old).delete()
            from .tronc_commun import nouvel_identifiant
            groupes = {}
            for ed in source.select_related("module", "classe").order_by("tronc_commun", "id"):
                if ed.tronc_commun and ed.tronc_commun not in groupes:
                    groupes[ed.tronc_commun] = nouvel_identifiant()
                copie = EmploiDuTemps(
                    tronc_commun=groupes.get(ed.tronc_commun) if ed.tronc_commun else None,
                    filiere_id=ed.filiere_id, niveau_id=ed.niveau_id, classe_id=ed.classe_id,
                    module_id=ed.module_id, formateur_id=ed.formateur_id, jour=ed.jour,
                    heure_debut=ed.heure_debut, heure_fin=ed.heure_fin, salle_id=ed.salle_id,
                    date_debut=cible_debut, date_fin=cible_fin,
                )
                try:
                    copie.save()
                    crees += 1
                except DjangoValidationError as e:
                    erreurs.append(f"{ed.jour} {ed.heure_debut:%H:%M}-{ed.heure_fin:%H:%M} {ed.module.nom} : {' '.join(e.messages)}")
        return Response({"crees": crees, "erreurs": erreurs}, status=201 if crees else 400)

    # ------------------------------------------------------------------
    # Validation des séances (heures comptabilisées seulement après validation)
    # ------------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="seances")
    def seances(self, request):
        """Séances datées d'une période avec leur état de validation.

        ?date_debut&date_fin (défaut : semaine en cours), ?classe, ?formateur, ?module,
        ?statut=a_valider|effectuee|non_effectuee|a_venir
        """
        import datetime as dt
        from academique.middleware import get_current_academic_year_id
        from .seances import annee_academique, lister_seances, maintenant

        params = request.query_params
        now = maintenant()
        annee = annee_academique(get_current_academic_year_id())
        debut = self._parse_date(params.get("date_debut"))
        fin = self._parse_date(params.get("date_fin"))
        if not debut and not fin:
            debut, fin = semaine_de(now.date())
        debut = debut or fin - dt.timedelta(days=6)
        fin = fin or debut + dt.timedelta(days=6)
        if (fin - debut).days > 370:
            return Response({"detail": "Période trop longue (1 an maximum)."}, status=400)

        qs = EmploiDuTemps.objects.filter(periode_q(debut, fin))
        srs = SeanceRealisee.objects.all()
        if annee:
            qs = qs.filter(classe__annee_academique=annee)
            srs = srs.filter(classe__annee_academique=annee)
        for key in ("classe", "formateur", "module"):
            if params.get(key):
                qs = qs.filter(**{f"{key}_id": params.get(key)})
                srs = srs.filter(**{f"{key}_id": params.get(key)})
        return Response(lister_seances(qs, srs, debut, fin, annee, now, params.get("statut")))

    @action(detail=False, methods=["post"], url_path="seances/valider")
    def valider_seances(self, request):
        """Valide (ou annule la validation) d'une ou plusieurs séances.

        Body : {"seances": [{"emploi_id", "date", "statut": "effectuee"|"non_effectuee"|"annuler",
                             "duree_minutes"?, "commentaire"?}]}
        """
        from django.utils.dateparse import parse_date
        from academique.middleware import get_current_academic_year_id
        from .seances import annee_academique, date_valide_pour, duree_prevue, est_passee, maintenant

        items = request.data.get("seances") or []
        if not isinstance(items, list) or not items:
            return Response({"detail": "Aucune séance à valider."}, status=400)
        now = maintenant()
        annee = annee_academique(get_current_academic_year_id())
        ok, erreurs = 0, []
        for it in items:
            try:
                e = EmploiDuTemps.objects.select_related("classe").get(pk=it.get("emploi_id"))
            except (EmploiDuTemps.DoesNotExist, ValueError, TypeError):
                erreurs.append(f"Créneau {it.get('emploi_id')} introuvable.")
                continue
            d = parse_date(str(it.get("date") or ""))
            label = f"{e.module} — {e.classe} du {d.strftime('%d-%m-%Y') if d else '?'}"
            statut = it.get("statut")
            if not d or not date_valide_pour(e, d, annee or (e.classe.annee_academique if e.classe else None)):
                erreurs.append(f"{label} : cette date ne correspond pas au créneau.")
                continue
            groupe = [e]
            if e.tronc_commun:
                # Une séance en tronc commun est validée pour toutes les classes du groupe
                groupe += [m for m in EmploiDuTemps.objects.filter(tronc_commun=e.tronc_commun).exclude(pk=e.pk)
                           if date_valide_pour(m, d, annee or (m.classe.annee_academique if m.classe else None))]
            if statut == "annuler":
                SeanceRealisee.objects.filter(emploi__in=groupe, date=d).delete()
                ok += 1
                continue
            if statut not in (SeanceRealisee.EFFECTUEE, SeanceRealisee.NON_EFFECTUEE):
                erreurs.append(f"{label} : statut invalide.")
                continue
            if not est_passee(d, e.heure_fin, now):
                erreurs.append(f"{label} : la séance n'est pas encore terminée.")
                continue
            prevue = duree_prevue(e)
            duree = prevue
            if statut == SeanceRealisee.EFFECTUEE and it.get("duree_minutes") not in (None, ""):
                try:
                    duree = int(it.get("duree_minutes"))
                except (TypeError, ValueError):
                    erreurs.append(f"{label} : durée invalide.")
                    continue
                if duree <= 0 or duree > 24 * 60:
                    erreurs.append(f"{label} : durée invalide.")
                    continue
            for m in groupe:
                SeanceRealisee.objects.update_or_create(
                    emploi=m, date=d,
                    defaults={
                        "statut": statut, "formateur_id": m.formateur_id, "module_id": m.module_id, "classe_id": m.classe_id,
                        "heure_debut": m.heure_debut, "heure_fin": m.heure_fin,
                        "duree_minutes": duree if statut == SeanceRealisee.EFFECTUEE else 0,
                        "commentaire": str(it.get("commentaire") or "")[:2000],
                        "valide_par": request.user if request.user.is_authenticated else None,
                    },
                )
            ok += 1
        return Response({"traitees": ok, "erreurs": erreurs}, status=200 if ok else 400)

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """Récupère l'emploi du temps de l'étudiant connecté."""
        etudiant = getattr(request.user, 'etudiant_profile', None)
        if not etudiant:
            return Response({"error": "Profil étudiant introuvable"}, status=404)
        
        # On récupère les emplois du temps liés à la classe de l'étudiant
        from academique.middleware import get_current_academic_year_id
        inscriptions = etudiant.inscriptions.all()
        year_id = get_current_academic_year_id()
        if year_id:
            de_l_annee = inscriptions.filter(models.Q(annee_academique_ref_id=year_id) | models.Q(classe__annee_academique_id=year_id))
            if de_l_annee.exists():
                inscriptions = de_l_annee
        classe_ids = inscriptions.values_list('classe_id', flat=True)
        niveau_ids = inscriptions.values_list('niveau_id', flat=True)
        
        queryset = EmploiDuTemps.objects.filter(
            models.Q(classe_id__in=classe_ids) | 
            models.Q(niveau_id__in=niveau_ids, classe__isnull=True)
        )
        # Par défaut : la semaine en cours (ou celle de ?date=YYYY-MM-DD) + les créneaux permanents
        from django.utils import timezone
        jour = self._parse_date(request.query_params.get("date")) or timezone.localdate()
        queryset = queryset.filter(periode_q(*semaine_de(jour)))
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # Création / modification avec tronc commun
    # ------------------------------------------------------------------
    def _enregistrer(self, serializer):
        from django.db import transaction
        from .tronc_commun import nouvel_identifiant, synchroniser

        classes = serializer.validated_data.pop("classes_tronc_commun", None)
        inst = serializer.instance
        classe = serializer.validated_data.get("classe", getattr(inst, "classe", None))
        autres = [int(c) for c in (classes or []) if c and (not classe or int(c) != classe.pk)]
        a_rattacher = getattr(serializer, "_a_rattacher", None) or []
        try:
            with transaction.atomic():
                kwargs = {}
                groupe = getattr(inst, "tronc_commun", None)
                if autres and not groupe:
                    groupe = nouvel_identifiant()
                    kwargs["tronc_commun"] = groupe
                if a_rattacher and groupe:
                    EmploiDuTemps.objects.filter(pk__in=a_rattacher).update(tronc_commun=groupe)
                obj = serializer.save(**kwargs)
                if classes is not None or obj.tronc_commun:
                    self.resultat_tronc_commun = synchroniser(obj, autres if classes is not None else None)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"non_field_errors": e.messages})

    def perform_create(self, serializer):
        self._enregistrer(serializer)

    def perform_update(self, serializer):
        self._enregistrer(serializer)

    def destroy(self, request, *args, **kwargs):
        """?tout_le_tronc_commun=1 : supprime le créneau pour toutes les classes du tronc commun."""
        from django.db import transaction
        obj = self.get_object()
        tout = str(request.query_params.get("tout_le_tronc_commun", "")).lower() in ("1", "true", "oui")
        with transaction.atomic():
            if tout and obj.tronc_commun:
                nb = EmploiDuTemps.objects.filter(tronc_commun=obj.tronc_commun).delete()[0]
            else:
                obj.delete()
                nb = 1
        return Response({"supprimes": nb}, status=200)

    @action(detail=False, methods=["get"], url_path="tronc-commun/classes")
    def tronc_commun_classes(self, request):
        """Classes pouvant suivre le cours en tronc commun.

        ?module=&classe=&jour=&heure_debut=HH:MM&heure_fin=HH:MM&date_debut=&date_fin=&emploi=<id en modification>
        """
        from django.utils.dateparse import parse_time
        from academique.models import Classe
        from .tronc_commun import classes_candidates

        p = request.query_params
        if not p.get("module"):
            return Response({"detail": "Le cours est requis."}, status=400)
        classe = Classe.objects.filter(pk=p.get("classe")).first() if p.get("classe") else None
        emploi = EmploiDuTemps.objects.filter(pk=p.get("emploi")).first() if p.get("emploi") else None
        hd = parse_time(p.get("heure_debut") or "") if p.get("heure_debut") else None
        hf = parse_time(p.get("heure_fin") or "") if p.get("heure_fin") else None
        return Response({"classes": classes_candidates(
            int(p["module"]), classe, p.get("jour"), hd, hf,
            self._parse_date(p.get("date_debut")), self._parse_date(p.get("date_fin")), emploi,
        )})

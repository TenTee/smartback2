from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import date
from decimal import Decimal

from .models import (
    Paie, ParametresPaie, Prime, Retenue,
    AvanceSalaire, CampagnePaie, BulletinPaie
)
from .serializers import (
    PaieSerializer, ParametresPaieSerializer, PrimeSerializer,
    RetenueSerializer, AvanceSalaireSerializer,
    CampagnePaieSerializer, CampagnePaieListSerializer, BulletinPaieSerializer
)
from personnels.models import Personnel
from formateurs.models import Formateur


class PaieViewSet(viewsets.ModelViewSet):
    queryset = Paie.objects.all().order_by('-date')
    serializer_class = PaieSerializer


class PrimeViewSet(viewsets.ModelViewSet):
    queryset = Prime.objects.all()
    serializer_class = PrimeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        ct = self.request.query_params.get('content_type')
        obj_id = self.request.query_params.get('object_id')
        if ct and obj_id:
            qs = qs.filter(beneficiaire_content_type_id=ct, beneficiaire_object_id=obj_id)
        return qs


class RetenueViewSet(viewsets.ModelViewSet):
    queryset = Retenue.objects.all()
    serializer_class = RetenueSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        ct = self.request.query_params.get('content_type')
        obj_id = self.request.query_params.get('object_id')
        if ct and obj_id:
            qs = qs.filter(beneficiaire_content_type_id=ct, beneficiaire_object_id=obj_id)
        return qs


class AvanceSalaireViewSet(viewsets.ModelViewSet):
    queryset = AvanceSalaire.objects.all()
    serializer_class = AvanceSalaireSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        ct = self.request.query_params.get('content_type')
        obj_id = self.request.query_params.get('object_id')
        if ct and obj_id:
            qs = qs.filter(beneficiaire_content_type_id=ct, beneficiaire_object_id=obj_id)
        return qs


class BulletinPaieViewSet(viewsets.ModelViewSet):
    queryset = BulletinPaie.objects.all()
    serializer_class = BulletinPaieSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        mois = self.request.query_params.get('mois')
        annee = self.request.query_params.get('annee')
        campagne = self.request.query_params.get('campagne')
        ct = self.request.query_params.get('content_type')
        obj_id = self.request.query_params.get('object_id')
        if mois:
            qs = qs.filter(mois=mois)
        if annee:
            qs = qs.filter(annee=annee)
        if campagne:
            qs = qs.filter(campagne_id=campagne)
        if ct and obj_id:
            qs = qs.filter(beneficiaire_content_type_id=ct, beneficiaire_object_id=obj_id)
        return qs


class CampagnePaieViewSet(viewsets.ModelViewSet):
    queryset = CampagnePaie.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return CampagnePaieListSerializer
        return CampagnePaieSerializer


class GenererCampagneView(APIView):
    """
    Génère une campagne de paie complète pour un mois/année donné.
    Crée automatiquement les bulletins pour tous les personnels et formateurs actifs.
    """
    def post(self, request):
        mois = request.data.get('mois')
        annee = request.data.get('annee')

        if not mois or not annee:
            return Response({"error": "mois et annee sont requis"}, status=status.HTTP_400_BAD_REQUEST)

        mois = int(mois)
        annee = int(annee)

        if CampagnePaie.objects.filter(mois=mois, annee=annee).exists():
            return Response(
                {"error": f"Une campagne existe déjà pour {mois:02d}/{annee}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        campagne = CampagnePaie.objects.create(mois=mois, annee=annee)

        personnel_ct = ContentType.objects.get_for_model(Personnel)
        formateur_ct = ContentType.objects.get_for_model(Formateur)

        total_brut = Decimal('0')
        total_primes_camp = Decimal('0')
        total_retenues_camp = Decimal('0')
        total_net = Decimal('0')
        count = 0

        all_beneficiaires = []
        for p in Personnel.objects.all():
            all_beneficiaires.append((personnel_ct, p))
        for f in Formateur.objects.all():
            all_beneficiaires.append((formateur_ct, f))

        today = date.today()

        for ct, beneficiaire in all_beneficiaires:
            salaire_base = Decimal(str(beneficiaire.salaire or 0))
            if salaire_base <= 0:
                continue

            primes = Prime.objects.filter(
                beneficiaire_content_type=ct,
                beneficiaire_object_id=beneficiaire.id,
                est_active=True,
            ).filter(
                Q(est_permanente=True) |
                Q(date_debut__lte=today, date_fin__gte=today)
            )

            retenues = Retenue.objects.filter(
                beneficiaire_content_type=ct,
                beneficiaire_object_id=beneficiaire.id,
                est_active=True,
            ).filter(
                Q(est_permanente=True) |
                Q(date_debut__lte=today, date_fin__gte=today)
            )

            detail_primes = [
                {"type": p.get_type_prime_display(), "libelle": p.libelle, "montant": float(p.montant)}
                for p in primes
            ]
            detail_retenues = [
                {"type": r.get_type_retenue_display(), "libelle": r.libelle, "montant": float(r.montant)}
                for r in retenues
            ]

            avances_en_cours = AvanceSalaire.objects.filter(
                beneficiaire_content_type=ct,
                beneficiaire_object_id=beneficiaire.id,
                statut="en_cours",
            )
            for avance in avances_en_cours:
                if avance.solde_restant > 0:
                    echeance = min(avance.montant_echeance, avance.solde_restant)
                    detail_retenues.append({
                        "type": "Remboursement avance",
                        "libelle": f"Avance du {avance.date_demande}",
                        "montant": float(echeance)
                    })

            sum_primes = sum(Decimal(str(p['montant'])) for p in detail_primes)
            sum_retenues = sum(Decimal(str(r['montant'])) for r in detail_retenues)

            bulletin = BulletinPaie.objects.create(
                campagne=campagne,
                beneficiaire_content_type=ct,
                beneficiaire_object_id=beneficiaire.id,
                mois=mois,
                annee=annee,
                salaire_base=salaire_base,
                total_primes=sum_primes,
                total_retenues=sum_retenues,
                detail_primes=detail_primes,
                detail_retenues=detail_retenues,
            )

            total_brut += bulletin.salaire_brut
            total_primes_camp += sum_primes
            total_retenues_camp += sum_retenues
            total_net += bulletin.salaire_net
            count += 1

        campagne.total_brut = total_brut
        campagne.total_primes = total_primes_camp
        campagne.total_retenues = total_retenues_camp
        campagne.total_net = total_net
        campagne.nombre_bulletins = count
        campagne.save()

        serializer = CampagnePaieSerializer(campagne)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ValiderCampagneView(APIView):
    def post(self, request, pk):
        try:
            campagne = CampagnePaie.objects.get(pk=pk)
        except CampagnePaie.DoesNotExist:
            return Response({"error": "Campagne non trouvée"}, status=status.HTTP_404_NOT_FOUND)

        if campagne.statut != "brouillon":
            return Response({"error": "Seule une campagne en brouillon peut être validée"}, status=status.HTTP_400_BAD_REQUEST)

        campagne.statut = "validee"
        campagne.date_validation = timezone.now()
        campagne.save()

        campagne.bulletins.update(statut="valide")

        return Response(CampagnePaieSerializer(campagne).data)


class PayerCampagneView(APIView):
    """
    Marque la campagne comme payée. Crée les dépenses correspondantes
    et met à jour les avances sur salaire.
    """
    def post(self, request, pk):
        try:
            campagne = CampagnePaie.objects.get(pk=pk)
        except CampagnePaie.DoesNotExist:
            return Response({"error": "Campagne non trouvée"}, status=status.HTTP_404_NOT_FOUND)

        if campagne.statut != "validee":
            return Response({"error": "La campagne doit être validée avant paiement"}, status=status.HTTP_400_BAD_REQUEST)

        from django.apps import apps
        Depense = apps.get_model('depenses', 'Depense')

        for bulletin in campagne.bulletins.all():
            bulletin.statut = "paye"
            bulletin.date_paiement = timezone.now()
            bulletin.save()

            beneficiaire_nom = getattr(bulletin.beneficiaire, 'nom', 'N/A') if bulletin.beneficiaire else 'N/A'
            Depense.objects.create(
                libelle=f"Salaire - {beneficiaire_nom} ({bulletin.mois:02d}/{bulletin.annee})",
                montant=bulletin.salaire_net,
                categorie="Autres",
                date_depense=timezone.now().date(),
                statut="Validée",
                responsable_content_type=bulletin.beneficiaire_content_type,
                responsable_object_id=bulletin.beneficiaire_object_id
            )

            for retenue in bulletin.detail_retenues:
                if "avance" in retenue.get("type", "").lower():
                    avances = AvanceSalaire.objects.filter(
                        beneficiaire_content_type=bulletin.beneficiaire_content_type,
                        beneficiaire_object_id=bulletin.beneficiaire_object_id,
                        statut="en_cours",
                    )
                    for avance in avances:
                        montant_retenu = Decimal(str(retenue['montant']))
                        avance.montant_rembourse += montant_retenu
                        avance.save()
                        break

        campagne.statut = "payee"
        campagne.date_paiement = timezone.now()
        campagne.save()

        return Response(CampagnePaieSerializer(campagne).data)


class PaieForecastView(APIView):
    def get(self, request):
        today = timezone.now().date()
        month = today.month
        year = today.year

        total_personnel = Personnel.objects.aggregate(total=Sum('salaire'))['total'] or 0
        total_formateurs = Formateur.objects.aggregate(total=Sum('salaire'))['total'] or 0
        total_previsionnel = total_personnel + total_formateurs

        total_paye = Paie.objects.filter(
            date__month=month, date__year=year, statut="Payé"
        ).aggregate(total=Sum('salaire'))['total'] or 0

        bulletins_payes = BulletinPaie.objects.filter(
            mois=month, annee=year, statut="paye"
        ).aggregate(total=Sum('salaire_net'))['total'] or 0

        total_paye_global = Decimal(str(total_paye)) + Decimal(str(bulletins_payes))

        config = ParametresPaie.objects.first()
        jour_paie = config.jour_de_paie if config else 25

        prochaine_paie = date(year, month, min(jour_paie, 28))
        if today > prochaine_paie:
            if month == 12:
                prochaine_paie = date(year + 1, 1, min(jour_paie, 28))
            else:
                prochaine_paie = date(year, month + 1, min(jour_paie, 28))

        nb_personnel = Personnel.objects.filter(salaire__gt=0).count()
        nb_formateurs = Formateur.objects.filter(salaire__gt=0).count()

        total_primes_actives = Prime.objects.filter(est_active=True).aggregate(
            total=Sum('montant'))['total'] or 0
        total_retenues_actives = Retenue.objects.filter(est_active=True).aggregate(
            total=Sum('montant'))['total'] or 0

        return Response({
            "total_previsionnel": float(total_previsionnel),
            "total_paye_mois": float(total_paye_global),
            "reste_a_payer": float(max(0, Decimal(str(total_previsionnel)) - total_paye_global)),
            "jour_de_paie": jour_paie,
            "prochaine_echeance": prochaine_paie,
            "is_near_payday": 0 <= (prochaine_paie - today).days <= 5,
            "nb_personnel": nb_personnel,
            "nb_formateurs": nb_formateurs,
            "total_primes_actives": float(total_primes_actives),
            "total_retenues_actives": float(total_retenues_actives),
            "taux_cnps_employe": float(config.taux_cnps_employe) if config else 4.2,
            "taux_cnps_employeur": float(config.taux_cnps_employeur) if config else 16.67,
            "taux_irpp": float(config.taux_irpp) if config else 10.0,
        })

    def post(self, request):
        jour = request.data.get("jour_de_paie")
        if jour is not None:
            config, created = ParametresPaie.objects.get_or_create(id=1)
            config.jour_de_paie = int(jour)
            if 'taux_cnps_employe' in request.data:
                config.taux_cnps_employe = request.data['taux_cnps_employe']
            if 'taux_cnps_employeur' in request.data:
                config.taux_cnps_employeur = request.data['taux_cnps_employeur']
            if 'taux_irpp' in request.data:
                config.taux_irpp = request.data['taux_irpp']
            config.save()
            return Response({"message": "Paramètres mis à jour", "jour_de_paie": config.jour_de_paie})
        return Response({"error": "Données invalides"}, status=400)


class ContentTypeView(APIView):
    def get(self, request):
        return Response({
            "personnel": ContentType.objects.get(app_label="personnels", model="personnel").id,
            "formateur": ContentType.objects.get(app_label="formateurs", model="formateur").id,
        })


class StatistiquesPaieView(APIView):
    """
    Statistiques globales de la paie : historique mensuel, répartition, évolution.
    """
    def get(self, request):
        annee = request.query_params.get('annee', timezone.now().year)
        annee = int(annee)

        campagnes = CampagnePaie.objects.filter(annee=annee).order_by('mois')
        historique = []
        for c in campagnes:
            historique.append({
                "mois": c.mois,
                "annee": c.annee,
                "total_brut": float(c.total_brut),
                "total_net": float(c.total_net),
                "total_primes": float(c.total_primes),
                "total_retenues": float(c.total_retenues),
                "nombre_bulletins": c.nombre_bulletins,
                "statut": c.statut,
            })

        masse_salariale_annuelle = CampagnePaie.objects.filter(
            annee=annee, statut="payee"
        ).aggregate(total=Sum('total_net'))['total'] or 0

        avances_en_cours = AvanceSalaire.objects.filter(statut="en_cours")
        total_avances = avances_en_cours.aggregate(total=Sum('montant_total'))['total'] or 0
        total_rembourse = avances_en_cours.aggregate(total=Sum('montant_rembourse'))['total'] or 0

        return Response({
            "annee": annee,
            "historique_mensuel": historique,
            "masse_salariale_annuelle": float(masse_salariale_annuelle),
            "total_avances_en_cours": float(total_avances),
            "total_avances_remboursees": float(total_rembourse),
            "nb_campagnes": campagnes.count(),
        })

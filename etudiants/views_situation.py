from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from decimal import Decimal

from .models import Etudiant, Inscription
from .serializers import EtudiantSerializer, InscriptionSerializer
from academique.middleware import get_current_academic_year_id

class StudentSituationView(APIView):
    """
    Vue consolidée pour le portail étudiant.
    Renvoie le profil, l'inscription, les notes, les finances et l'assiduité
    pour l'année académique sélectionnée.
    """
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Non authentifié"}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            etudiant = getattr(request.user, 'etudiant_profile', None)
            if not etudiant:
                return Response({"error": "Profil étudiant introuvable"}, status=status.HTTP_404_NOT_FOUND)
            
            year_id = get_current_academic_year_id()
            
            # 1. Inscription pour l'année sélectionnée
            if year_id:
                inscription = etudiant.inscriptions.filter(annee_academique_ref_id=year_id).first()
            else:
                inscription = etudiant.inscriptions.order_by("-date_inscription").first()
            
            # 2. Résumé des notes (via application notes)
            from notes.models import Note
            notes_qs = Note.objects.filter(etudiant=etudiant)
            if year_id:
                notes_qs = notes_qs.filter(classe__annee_academique_id=year_id)
            
            # On prend les 5 dernières notes ou un résumé par session
            notes_summary = []
            for n in notes_qs.select_related("module").order_by("-id")[:10]:
                notes_summary.append({
                    "id": n.id,
                    "module": n.module.nom,
                    "note_finale": n.note_finale,
                    "session": n.session,
                    "date": n.created_at if hasattr(n, 'created_at') else None
                })
            
            # 3. Résumé financier (via application paiements)
            from paiements.models import Paiement, Frais
            montant_du = Decimal("0")
            montant_paye = Decimal("0")
            
            if inscription and inscription.classe:
                from django.db.models import DecimalField
                frais_classe = Frais.objects.filter(classe=inscription.classe)
                montant_du = frais_classe.aggregate(total=Coalesce(Sum("montant"), Decimal("0"), output_field=DecimalField()))["total"]
                
                paiements_qs = Paiement.objects.filter(etudiant=etudiant, frais__classe=inscription.classe)
                montant_paye = paiements_qs.aggregate(total=Coalesce(Sum("montant_paye"), Decimal("0"), output_field=DecimalField()))["total"]
            
            # 4. Résumé assiduité (via application assiduite)
            from assiduite.models import AssiduiteRecord
            assiduite_qs = AssiduiteRecord.objects.filter(etudiant=etudiant)
            if year_id:
                # Filtrer par date si possible, ou par inscription
                if inscription:
                     # On pourrait filtrer par dates de l'année académique si on les avait
                     # Pour l'instant on filtre par le lien indirect
                     assiduite_qs = assiduite_qs.filter(etudiant__inscriptions__annee_academique_ref_id=year_id)
            
            absences = assiduite_qs.filter(type="ABSENCE").count()
            retards = assiduite_qs.filter(type="RETARD").count()
            
            return Response({
                "etudiant": EtudiantSerializer(etudiant).data,
                "inscription": InscriptionSerializer(inscription).data if inscription else None,
                "est_inscrit": inscription is not None,
                "notes_summary": notes_summary,
                "finances": {
                    "montant_du": float(montant_du),
                    "montant_paye": float(montant_paye),
                    "solde": float(montant_du - montant_paye)
                },
                "assiduite": {
                    "absences": absences,
                    "retards": retards
                }
            })
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class StudentHistoryView(APIView):
    """
    Vue complète de l'historique de l'étudiant.
    Renvoie une liste de situations, groupées par année académique.
    """
    def get(self, request):
        from notes.models import Note
        from paiements.models import Paiement, Frais
        from assiduite.models import AssiduiteRecord
        from django.db.models import Sum, DecimalField
        from django.db.models.functions import Coalesce
        from decimal import Decimal

        if not request.user.is_authenticated:
            return Response({"error": "Non authentifié"}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            etudiant = getattr(request.user, 'etudiant_profile', None)
            if not etudiant:
                return Response({"error": "Profil étudiant introuvable"}, status=404)
            
            history = []
            # On récupère toutes les inscriptions de l'étudiant
            inscriptions = etudiant.inscriptions.select_related("annee_academique_ref", "classe", "niveau").order_by("-annee_academique_ref__libelle")
            
            for ins in inscriptions:
                year = ins.annee_academique_ref
                year_id = year.id if year else None
                
                # Situation pour cette année spécifique
                # 1. Notes (count only for history summary)
                notes_qs = Note.objects.filter(etudiant=etudiant)
                if year_id:
                    notes_qs = notes_qs.filter(classe__annee_academique_id=year_id)
                
                # 2. Finances
                montant_du = Decimal("0")
                montant_paye = Decimal("0")
                if ins.classe:
                    frais_classe = Frais.objects.filter(classe=ins.classe)
                    montant_du = frais_classe.aggregate(total=Coalesce(Sum("montant"), Decimal("0"), output_field=DecimalField()))["total"]
                    
                    paiements_qs = Paiement.objects.filter(etudiant=etudiant, frais__classe=ins.classe)
                    montant_paye = paiements_qs.aggregate(total=Coalesce(Sum("montant_paye"), Decimal("0"), output_field=DecimalField()))["total"]
                
                # 3. Assiduité
                assiduite_qs = AssiduiteRecord.objects.filter(etudiant=etudiant)
                if year_id:
                    assiduite_qs = assiduite_qs.filter(etudiant__inscriptions__annee_academique_ref_id=year_id)
                
                history.append({
                    "annee_academique": ins.annee_academique_ref_libelle or ins.annee_academique,
                    "annee_academique_id": year_id,
                    "classe": ins.classe_nom,
                    "niveau": ins.niveau_nom,
                    "notes_count": notes_qs.count(),
                    "finances": {
                        "montant_du": float(montant_du),
                        "montant_paye": float(montant_paye),
                        "solde": float(montant_du - montant_paye)
                    },
                    "assiduite": {
                        "absences": assiduite_qs.filter(type="ABSENCE").count(),
                        "retards": assiduite_qs.filter(type="RETARD").count()
                    }
                })
                
            return Response({
                "etudiant": EtudiantSerializer(etudiant).data,
                "history": history
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

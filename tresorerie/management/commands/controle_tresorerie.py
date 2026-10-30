"""Contrôle de la trésorerie (lecture seule) : composition de chaque compte et anomalies probables.

    python manage.py controle_tresorerie
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum


def f(v):
    return f"{Decimal(v or 0):,.0f}".replace(",", " ") + " FCFA"


class Command(BaseCommand):
    help = "Affiche d'où vient le solde de chaque caisse / compte et signale les anomalies probables (rien n'est modifié)."

    def handle(self, *args, **opts):
        from paiements.models import Paiement
        from paiements.frais_etudiant import frais_etudiant
        from etudiants.models import Inscription

        from tresorerie.models import CompteTresorerie, Operation

        for c in CompteTresorerie.objects.all():
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {c.nom} : solde {f(c.solde())} (solde initial {f(c.solde_initial)})"))
            rows = (Operation.objects.filter(compte=c, statut="validee").exclude(type="virement")
                    .values("type", "source", "categorie__libelle").annotate(t=Sum("montant"), n=Count("id")).order_by("type", "-t"))
            for r in rows:
                signe = "+" if r["type"] == "recette" else "-"
                self.stdout.write(f"  {signe} {f(r['t']):>18}  {r['n']:>5} op.  {r['source']:<10} {r['categorie__libelle'] or ''}")
            vin = Operation.objects.filter(compte_destination=c, statut="validee", type="virement").aggregate(t=Sum("montant"))["t"]
            vout = Operation.objects.filter(compte=c, statut="validee", type="virement").aggregate(t=Sum("montant"))["t"]
            if vin or vout:
                self.stdout.write(f"  virements reçus {f(vin)} / envoyés {f(vout)}")

        attente = Operation.objects.filter(type="recette", statut="en_attente")
        if attente.exists():
            t = attente.aggregate(t=Sum("montant"))["t"]
            self.stdout.write(self.style.WARNING(f"\nRecettes à valider (non comptées en caisse) : {attente.count()} pour {f(t)}"))

        # Étudiants dont les paiements dépassent les frais dus : saisie du montant total au lieu du versement ?
        self.stdout.write(self.style.MIGRATE_HEADING("\n== Paiements supérieurs aux frais dus"))
        payes = defaultdict(Decimal)
        for p in Paiement.objects.values("etudiant_id", "annee_academique_id").annotate(t=Sum("montant_paye")):
            payes[(p["etudiant_id"], p["annee_academique_id"])] += p["t"] or 0
        n = 0
        for ins in Inscription.objects.select_related("etudiant", "classe").filter(classe__isnull=False):
            paye = payes.get((ins.etudiant_id, ins.annee_academique_ref_id))
            if not paye:
                continue
            try:
                du = frais_etudiant(ins.etudiant, ins.classe)["total"]
            except Exception:  # noqa: BLE001
                continue
            if du and paye > du:
                n += 1
                self.stdout.write(f"  {ins.etudiant.nom} ({ins.classe.nom}) : payé {f(paye)} pour {f(du)} dus")
        if not n:
            self.stdout.write("  aucun")

        test = Operation.objects.filter(libelle__startswith="Revenu divers").exclude(statut="annulee")
        if test.exists():
            self.stdout.write(self.style.WARNING(f"\n{test.count()} opération(s) « Revenu divers N » : données de test probables (scripts/populate_finances.py)."))
        self.stdout.write("\nAucune donnée n'a été modifiée.")

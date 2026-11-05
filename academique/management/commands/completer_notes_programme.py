"""
Crée les lignes de notes manquantes pour que chaque étudiant inscrit ait une ligne par module
du programme de sa classe (les classes complétées après les inscriptions en manquaient).

    python manage.py completer_notes_programme            # toutes les classes
    python manage.py completer_notes_programme --classe 12
    python manage.py completer_notes_programme --dry-run  # simulation
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from etudiants.models import Inscription
from etudiants.signals import creer_note_vide
from notes.models import Note


class Command(BaseCommand):
    help = "Complète les lignes de notes des étudiants avec tous les modules du programme de leur classe."

    def add_arguments(self, parser):
        parser.add_argument("--classe", type=int, help="Limiter à une classe (id)")
        parser.add_argument("--dry-run", action="store_true", help="Afficher sans rien créer")

    def handle(self, *args, **opts):
        inscriptions = Inscription.objects.filter(classe__isnull=False).select_related("etudiant", "classe")
        if opts.get("classe"):
            inscriptions = inscriptions.filter(classe_id=opts["classe"])
        total = 0
        with transaction.atomic():
            for ins in inscriptions:
                manquants = [m for m in ins.classe.modules.all()
                             if not Note.objects.filter(etudiant=ins.etudiant, module=m, classe=ins.classe).exists()]
                if not manquants:
                    continue
                total += len(manquants)
                self.stdout.write(f"{ins.etudiant.nom} ({ins.classe.nom}) : {len(manquants)} module(s) ajouté(s)")
                if not opts["dry_run"]:
                    for m in manquants:
                        creer_note_vide(ins.etudiant, m, ins.classe)
            if opts["dry_run"]:
                transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f"{total} ligne(s) de notes {'à créer' if opts['dry_run'] else 'créée(s)'}."))

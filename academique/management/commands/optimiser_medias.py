"""Optimise sur place les images déjà présentes dans MEDIA_ROOT (mêmes noms : aucun lien cassé).

    python manage.py optimiser_medias --dry-run     # estimation du gain, sans rien modifier
    python manage.py optimiser_medias               # optimisation
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from smart_back.medias import EXTENSIONS_IMAGES, _taille_max, optimiser_image


class Command(BaseCommand):
    help = "Redimensionne et recompresse les images existantes du dossier media (sur place)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Calculer le gain sans modifier les fichiers")

    def handle(self, *args, **opts):
        racine = str(settings.MEDIA_ROOT)
        nb, avant, apres = 0, 0, 0
        for dossier, _, fichiers in os.walk(racine):
            for f in fichiers:
                if os.path.splitext(f)[1].lower() not in EXTENSIONS_IMAGES:
                    continue
                chemin = os.path.join(dossier, f)
                relatif = os.path.relpath(chemin, racine).replace(os.sep, "/")
                with open(chemin, "rb") as fh:
                    donnees = fh.read()
                res = optimiser_image(donnees, f, _taille_max(relatif), conserver_format=True)
                if not res:
                    continue
                octets, _ = res
                nb += 1
                avant += len(donnees)
                apres += len(octets)
                self.stdout.write(f"{relatif} : {len(donnees) // 1024} Ko → {len(octets) // 1024} Ko")
                if not opts["dry_run"]:
                    tmp = chemin + ".tmp"
                    with open(tmp, "wb") as fh:
                        fh.write(octets)
                    os.replace(tmp, chemin)
        gain = (avant - apres) / 1024 / 1024
        verbe = "à optimiser" if opts["dry_run"] else "optimisée(s)"
        self.stdout.write(self.style.SUCCESS(f"{nb} image(s) {verbe} — gain : {gain:.1f} Mo"))

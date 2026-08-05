from django.core.management.base import BaseCommand
from django.db import transaction

from academique.models import Filiere, AnneeAcademique, Classe


class Command(BaseCommand):
    help = "Auto-generate Classe instances for filiere/cycle/niveau combinations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--annee",
            help="Année académique libelle to generate for (e.g., '2024-2025')",
            default=None,
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Generate for all années académiques",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without saving",
        )

    def handle(self, *args, **options):
        annee = options.get("annee")
        all_flag = options.get("all")
        dry_run = options.get("dry_run")

        if not all_flag and not annee:
            self.stdout.write(self.style.ERROR("Specify --annee or --all"))
            return

        années = AnneeAcademique.objects.all() if all_flag else AnneeAcademique.objects.filter(libelle=annee)
        if not années.exists():
            self.stdout.write(self.style.ERROR("No matching AnneeAcademique found"))
            return

        created = 0
        for an in années:
            for filiere in Filiere.objects.all():
                for cycle in filiere.cycles.all():
                    for niveau in cycle.niveaux.all():
                        exists = Classe.objects.filter(filiere=filiere, niveau=niveau, annee_academique=an).exists()
                        if exists:
                            continue
                        if dry_run:
                            self.stdout.write(f"Would create Classe for {filiere} / {cycle} / {niveau} / {an}")
                            continue

                        with transaction.atomic():
                            classe = Classe.objects.create(
                                filiere=filiere, cycle=cycle, niveau=niveau, annee_academique=an
                            )
                        created += 1
                        self.stdout.write(self.style.SUCCESS(f"Created Classe: {classe.nom}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Created {created} classes."))

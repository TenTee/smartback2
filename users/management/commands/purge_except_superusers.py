from django.core.management.base import BaseCommand
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction, connection


class Command(BaseCommand):
    help = "Delete all data from the database except superusers (keeps superuser rows in the user model)."

    def add_arguments(self, parser):
        parser.add_argument('--noinput', action='store_true', help='Run non-interactively')

    def handle(self, *args, **options):
        noinput = options.get('noinput', False)
        if not noinput:
            confirm = input("Cette opération supprimera définitivement toutes les données sauf les super-admins. Tapez 'OUI' pour continuer: ")
            if confirm != 'OUI':
                self.stdout.write(self.style.ERROR('Annulé par l\'utilisateur.'))
                return

        User = get_user_model()
        preserve_pks = list(User.objects.filter(is_superuser=True).values_list('pk', flat=True))
        self.stdout.write(f"Conserver {len(preserve_pks)} super-admin(s).")

        with transaction.atomic():
            # Try to disable foreign key checks for SQLite to avoid constraint issues
            try:
                cursor = connection.cursor()
                cursor.execute('PRAGMA foreign_keys = OFF;')
            except Exception:
                cursor = None

            for model in apps.get_models():
                # Skip unmanaged models
                if getattr(model._meta, 'managed', True) is False:
                    continue

                if model is User:
                    qs = model.objects.exclude(pk__in=preserve_pks)
                else:
                    qs = model.objects.all()

                if qs.exists():
                    count = qs.count()
                    qs.delete()
                    self.stdout.write(f"Supprimé {count} objets de {model._meta.label}.")

            # Re-enable foreign key checks if possible
            try:
                if cursor is not None:
                    cursor.execute('PRAGMA foreign_keys = ON;')
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS('Purge terminée.'))

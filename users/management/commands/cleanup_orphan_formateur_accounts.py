from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Supprime les comptes utilisateurs avec role='formateur' qui n'ont plus de profil formateur associe."

    def handle(self, *args, **options):
        User = get_user_model()

        orphans = User.objects.filter(
            role='formateur',
        ).exclude(
            formateur_profile__isnull=False,
        )

        count = orphans.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("Aucun compte formateur orphelin trouve."))
            return

        self.stdout.write(f"Suppression de {count} compte(s) formateur orphelin(s)...")
        for user in orphans:
            self.stdout.write(f"  - {user.username} ({user.email})")
        orphans.delete()
        self.stdout.write(self.style.SUCCESS(f"{count} compte(s) supprime(s)."))

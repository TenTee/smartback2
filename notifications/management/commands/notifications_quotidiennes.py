from django.core.management.base import BaseCommand

from notifications.verifications import executer


class Command(BaseCommand):
    help = "Envoie les rappels quotidiens (échéances en retard, séances à valider). À planifier chaque matin (cron)."

    def handle(self, *args, **options):
        res = executer(force=True)
        self.stdout.write(self.style.SUCCESS(f"Rappels envoyés : {res}"))

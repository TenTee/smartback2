import base64

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Génère une paire de clés VAPID pour les notifications push (à mettre dans le .env)."

    def handle(self, *args, **options):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        cle = ec.generate_private_key(ec.SECP256R1())
        prive = cle.private_numbers().private_value.to_bytes(32, "big")
        public = cle.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
        self.stdout.write("Ajoutez ces lignes au fichier .env du serveur :\n")
        self.stdout.write(f"VAPID_PUBLIC_KEY={b64(public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64(prive)}")
        self.stdout.write("VAPID_EMAIL=contact@votre-etablissement.com")

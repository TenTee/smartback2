from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create or update a superuser non-interactively'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True, help='Username for the superuser')
        parser.add_argument('--password', required=True, help='Password for the superuser')
        parser.add_argument('--email', required=False, default='admin@example.com', help='Email')
        parser.add_argument('--noms', required=False, default='', help='Noms (noms field)')
        parser.add_argument('--prenoms', required=False, default='', help='Prenoms (prenoms field)')

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']
        password = options['password']
        email = options['email']
        noms = options['noms'] or username
        prenoms = options['prenoms'] or ''

        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                'email': email,
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
                'noms': noms,
                'prenoms': prenoms,
            }
        )
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'Created superuser: {username}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Updated superuser: {username}'))

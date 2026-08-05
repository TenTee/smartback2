from django.apps import AppConfig


class FormateursConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'formateurs'

    def ready(self):
        import formateurs.signals  # noqa: F401

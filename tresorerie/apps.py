from django.apps import AppConfig


class TresorerieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tresorerie"
    verbose_name = "Trésorerie et comptabilité"

    def ready(self):
        from . import signals  # noqa: F401

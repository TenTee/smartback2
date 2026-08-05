from django.apps import AppConfig


class AcademiqueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academique"

    def ready(self):
        # Import signals to connect post_save handlers
        try:
            import academique.signals  # noqa: F401
        except Exception:
            # Avoid raising during manage.py commands that don't need app ready
            pass


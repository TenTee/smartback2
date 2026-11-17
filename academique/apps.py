from django.apps import AppConfig


class AcademiqueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academique"

    def ready(self):
        # Optimisation automatique des images importées (tous les modèles)
        from smart_back.medias import brancher
        brancher()
        # Import signals to connect post_save handlers
        try:
            import academique.signals  # noqa: F401
        except Exception:
            # Avoid raising during manage.py commands that don't need app ready
            pass


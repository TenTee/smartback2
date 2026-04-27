from django.apps import AppConfig


class EtudiantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'etudiants'
    
    def ready(self):
        import etudiants.signals  # ✅ Charger les signaux

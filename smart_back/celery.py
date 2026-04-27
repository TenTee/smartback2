# smart_back/celery.py
import os
from celery import Celery

# Indique à Celery où trouver les settings Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smart_back.settings")

app = Celery("smart_back")

# Charge la configuration depuis settings.py, avec préfixe CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Découvre automatiquement les tâches dans tes apps (tasks.py)
app.autodiscover_tasks()
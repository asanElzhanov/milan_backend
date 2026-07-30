import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('shop')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Use django-celery-beat's DatabaseScheduler
from celery.schedules import schedule
from django_celery_beat.schedulers import DatabaseScheduler

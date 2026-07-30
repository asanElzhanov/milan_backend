from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.orders'

    def ready(self):
        from .scheduler import start_scheduler

        try:
            start_scheduler()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f'Failed to start order scheduler: {e}')

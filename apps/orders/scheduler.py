import logging
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings

logger = logging.getLogger(__name__)
scheduler = None


def start_scheduler():
    global scheduler
    if scheduler is not None:
        return

    scheduler = BackgroundScheduler()

    check_minutes = getattr(settings, 'ORDER_EXPIRY_CHECK_MINUTES', 5)

    from .tasks import cancel_expired_orders

    scheduler.add_job(
        cancel_expired_orders,
        'interval',
        minutes=check_minutes,
        id='orders-cancel-expired',
        name='Cancel expired orders',
        replace_existing=True,
        max_instances=1,
    )

    try:
        scheduler.start()
        logger.info(f'Order scheduler started. Checking expired orders every {check_minutes} minutes.')
    except RuntimeError:
        logger.info('Order scheduler already running.')


def stop_scheduler():
    global scheduler
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info('Order scheduler stopped.')

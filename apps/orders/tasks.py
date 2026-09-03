import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Order
from .services import InvalidOrderStatusTransitionError, OrderStatusService

logger = logging.getLogger(__name__)


@shared_task(name='orders.cancel_expired_orders')
def cancel_expired_orders():
    """Авто-отмена неоплаченных заказов, у которых истекло время на оплату.

    Заказ считается просроченным, если он всё ещё ожидает оплаты и был создан
    более ``ORDER_PAYMENT_TIMEOUT_MINUTES`` минут назад. Такие заказы
    отменяются со статусом оплаты «Время оплаты истекло», а товары
    возвращаются в продажу.
    """
    timeout_minutes = getattr(settings, 'ORDER_PAYMENT_TIMEOUT_MINUTES', 30)
    if timeout_minutes <= 0:
        return {'status': 'disabled'}

    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
    order_ids = list(
        Order.objects.filter(
            status__in=[Order.Status.NEW, Order.Status.WAITING_PAYMENT],
            payment_status__in=[
                Order.PaymentStatus.UNPAID,
                Order.PaymentStatus.WAITING,
            ],
            created_at__lt=cutoff,
        )
        .order_by('created_at')
        .values_list('id', flat=True)
    )

    cancelled = 0
    for order_id in order_ids:
        try:
            OrderStatusService.cancel_order(
                order_id,
                comment='Автоматическая отмена: время оплаты истекло.',
                expired=True,
            )
            cancelled += 1
        except InvalidOrderStatusTransitionError:
            # Статус успел измениться между выборкой и блокировкой — пропускаем.
            continue
        except Exception:
            logger.exception('Failed to auto-cancel expired order %s', order_id)

    return {'status': 'ok', 'checked': len(order_ids), 'cancelled': cancelled}


@shared_task(name='orders.cancel_unpaid_order')
def cancel_unpaid_order(order_id):
    """Отменить конкретный заказ, если он всё ещё не оплачен.

    Планируется при создании заказа с задержкой
    ``ORDER_PAYMENT_TIMEOUT_MINUTES`` минут (``apply_async(countdown=...)``).
    Когда задача срабатывает, время на оплату уже истекло, поэтому проверять
    возраст заказа не нужно — достаточно убедиться, что он всё ещё ждёт оплаты.

    Идемпотентна: если заказ успели оплатить, отменить или он ушёл дальше по
    статусам — ничего не делает.
    """
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return {'status': 'not_found', 'order_id': order_id}

    if order.status not in (Order.Status.NEW, Order.Status.WAITING_PAYMENT):
        return {'status': 'skipped', 'order_id': order_id, 'reason': order.status}
    if order.payment_status not in (
        Order.PaymentStatus.UNPAID,
        Order.PaymentStatus.WAITING,
    ):
        return {'status': 'skipped', 'order_id': order_id, 'reason': order.payment_status}

    try:
        OrderStatusService.cancel_order(
            order_id,
            comment='Автоматическая отмена: время оплаты истекло.',
            expired=True,
        )
    except InvalidOrderStatusTransitionError:
        # Статус успел измениться между проверкой и блокировкой — это нормально.
        return {'status': 'skipped', 'order_id': order_id}
    except Exception:
        logger.exception('Failed to auto-cancel unpaid order %s', order_id)
        raise

    return {'status': 'cancelled', 'order_id': order_id}

import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_email(self, order_id):
    """Письмо покупателю при создании заказа"""
    try:
        from apps.orders.models import Order
        order = Order.objects.prefetch_related('items').get(pk=order_id)

        subject = f'Ваш заказ #{order.order_number} принят'
        html_message = render_to_string('emails/order_confirmation.html', {'order': order})

        send_mail(
            subject=subject,
            message=f'Ваш заказ #{order.order_number} принят. Сумма: {order.total_amount} ₸',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            html_message=html_message,
            fail_silently=False,
        )

        # Уведомление администратору
        send_mail(
            subject=f'[Новый заказ] #{order.order_number} на {order.total_amount} ₸',
            message=f'Новый заказ от {order.customer_name} {order.email}\nСумма: {order.total_amount} ₸',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
            fail_silently=True,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_paid_notification(self, order_id):
    """Письмо при успешной оплате"""
    try:
        from apps.orders.models import Order
        order = Order.objects.get(pk=order_id)

        send_mail(
            subject=f'Оплата подтверждена — заказ #{order.order_number}',
            message=f'Ваш заказ #{order.order_number} успешно оплачен. Мы начинаем его обрабатывать.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def send_otp_task(self, user_id, code, purpose):
    """Send an OTP code by email.

    SMS delivery is not integrated yet; phone verification uses email fallback.
    """
    try:
        user_model = get_user_model()
        user = user_model.objects.get(pk=user_id)
        if not user.email:
            logger.warning('Cannot send OTP: user_id=%s has no email', user_id)
            return

        purpose_note = ''
        if purpose == 'phone_verify':
            purpose_note = '\nThis code was requested for phone verification.'

        send_mail(
            subject='Your verification code',
            message=(
                f'Your verification code is: {code}\n\n'
                f'The code is valid for {settings.OTP_CODE_TTL_MINUTES} minutes.'
                f'{purpose_note}\n'
                'If you did not request this code, please ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except get_user_model().DoesNotExist:
        logger.warning('Cannot send OTP: user_id=%s does not exist', user_id)
    except Exception as exc:
        logger.exception('Failed to send OTP for user_id=%s', user_id)
        raise self.retry(exc=exc)

@shared_task
def send_order_status_update(order_id, new_status):
    """Уведомление об изменении статуса заказа"""
    from apps.orders.models import Order
    order = Order.objects.get(pk=order_id)

    status_labels = {
        'waiting_payment': 'ожидает оплаты',
        'paid': 'оплачен',
        'processing': 'в обработке',
        'shipped': 'отправлен',
        'completed': 'завершён',
    }
    label = status_labels.get(new_status, new_status)

    send_mail(
        subject=f'Статус заказа #{order.order_number} обновлён',
        message=f'Ваш заказ #{order.order_number} теперь {label}.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.email],
        fail_silently=True,
    )

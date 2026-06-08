from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_order_confirmation_email(self, order_id):
    """Письмо покупателю при создании заказа"""
    try:
        from apps.orders.models import Order
        order = Order.objects.prefetch_related('items').get(pk=order_id)

        subject = f'Ваш заказ #{order.number} принят'
        html_message = render_to_string('emails/order_confirmation.html', {'order': order})

        send_mail(
            subject=subject,
            message=f'Ваш заказ #{order.number} принят. Сумма: {order.total} ₸',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            html_message=html_message,
            fail_silently=False,
        )

        # Уведомление администратору
        send_mail(
            subject=f'[Новый заказ] #{order.number} на {order.total} ₸',
            message=f'Новый заказ от {order.first_name} {order.email}\nСумма: {order.total} ₸',
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
            subject=f'Оплата подтверждена — заказ #{order.number}',
            message=f'Ваш заказ #{order.number} успешно оплачен. Мы начинаем его обрабатывать.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def send_otp_task(self, user_id, code, purpose):
    """Отправить OTP код (email или SMS)"""
    try:
        from apps.accounts.models import User
        user = User.objects.get(pk=user_id)

        if purpose == 'email_verify':
            send_mail(
                subject='Код подтверждения',
                message=f'Ваш код: {code}. Действует 10 минут.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        elif purpose == 'phone_verify':
            # TODO: интегрировать SMS-провайдер (Nikita Mobile, SMS.kz и т.п.)
            pass
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def send_order_status_update(order_id, new_status):
    """Уведомление об изменении статуса заказа"""
    from apps.orders.models import Order
    order = Order.objects.get(pk=order_id)

    status_labels = {
        'confirmed': 'подтверждён',
        'processing': 'в обработке',
        'shipped': 'отправлен',
        'delivered': 'доставлен',
    }
    label = status_labels.get(new_status, new_status)

    send_mail(
        subject=f'Статус заказа #{order.number} обновлён',
        message=f'Ваш заказ #{order.number} теперь {label}.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.email],
        fail_silently=True,
    )

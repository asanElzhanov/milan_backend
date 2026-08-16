import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

from .email import send_email_logged
from .services import EmailNotificationService


logger = logging.getLogger(__name__)


def _retry_email_task(task, exc, message, *args):
    logger.exception(message, *args)
    raise task.retry(exc=exc)


def _send_order_created(order_id, retry_task):
    try:
        from apps.orders.models import Order

        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning('Cannot send order created email: order_id=%s does not exist', order_id)
        return
    if not EmailNotificationService._order_recipient_email(order):
        logger.warning('Cannot send order created email: order_id=%s has no email', order_id)
        return
    try:
        return EmailNotificationService.send_order_created_email(order)
    except Exception as exc:
        _retry_email_task(retry_task, exc, 'Failed to send order created email for order_id=%s', order_id)


def _send_order_paid(order_id, retry_task):
    try:
        from apps.orders.models import Order

        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning('Cannot send order paid email: order_id=%s does not exist', order_id)
        return
    if not EmailNotificationService._order_recipient_email(order):
        logger.warning('Cannot send order paid email: order_id=%s has no email', order_id)
        return
    try:
        return EmailNotificationService.send_order_paid_email(order)
    except Exception as exc:
        _retry_email_task(retry_task, exc, 'Failed to send order paid email for order_id=%s', order_id)


def _send_order_status_changed(order_id, retry_task, old_status=None, new_status=None):
    try:
        from apps.orders.models import Order

        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning(
            'Cannot send order status changed email: order_id=%s does not exist',
            order_id,
        )
        return
    if not EmailNotificationService._order_recipient_email(order):
        logger.warning(
            'Cannot send order status changed email: order_id=%s has no email',
            order_id,
        )
        return
    try:
        return EmailNotificationService.send_order_status_changed_email(
            order,
            old_status=old_status,
            new_status=new_status,
        )
    except Exception as exc:
        _retry_email_task(
            retry_task,
            exc,
            'Failed to send order status changed email for order_id=%s',
            order_id,
        )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_created_email',
)
def send_order_created_email(self, order_id):
    return _send_order_created(order_id, self)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_paid_email',
)
def send_order_paid_email(self, order_id):
    return _send_order_paid(order_id, self)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_status_changed_email',
)
def send_order_status_changed_email(self, order_id, old_status=None, new_status=None):
    return _send_order_status_changed(order_id, self, old_status=old_status, new_status=new_status)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_cancelled_email',
)
def send_order_cancelled_email(self, order_id):
    try:
        from apps.orders.models import Order

        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        logger.warning('Cannot send order cancelled email: order_id=%s does not exist', order_id)
        return
    if not EmailNotificationService._order_recipient_email(order):
        logger.warning('Cannot send order cancelled email: order_id=%s has no email', order_id)
        return
    try:
        return EmailNotificationService.send_order_cancelled_email(order)
    except Exception as exc:
        _retry_email_task(self, exc, 'Failed to send order cancelled email for order_id=%s', order_id)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_review_published_email',
)
def send_review_published_email(self, review_id):
    try:
        from apps.catalog.models import Review

        review = Review.objects.select_related('product', 'user').get(pk=review_id)
    except Review.DoesNotExist:
        logger.warning('Cannot send review published email: review_id=%s does not exist', review_id)
        return
    if not review.user.email:
        logger.warning('Cannot send review published email: review_id=%s has no user email', review_id)
        return
    try:
        return EmailNotificationService.send_review_published_email(review)
    except Exception as exc:
        _retry_email_task(
            self,
            exc,
            'Failed to send review published email for review_id=%s',
            review_id,
        )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_review_rejected_email',
)
def send_review_rejected_email(self, review_id):
    try:
        from apps.catalog.models import Review

        review = Review.objects.select_related('product', 'user').get(pk=review_id)
    except Review.DoesNotExist:
        logger.warning('Cannot send review rejected email: review_id=%s does not exist', review_id)
        return
    if not review.user.email:
        logger.warning('Cannot send review rejected email: review_id=%s has no user email', review_id)
        return
    try:
        return EmailNotificationService.send_review_rejected_email(review)
    except Exception as exc:
        _retry_email_task(
            self,
            exc,
            'Failed to send review rejected email for review_id=%s',
            review_id,
        )


@shared_task(bind=True, max_retries=3, name='notifications.send_otp')
def send_otp_task(self, user_id, code, purpose):
    """Send an OTP code by email.

    SMS delivery is not integrated yet; phone verification uses email fallback.
    """
    user_model = get_user_model()
    try:
        user = user_model.objects.get(pk=user_id)
        if not user.email:
            logger.warning('Cannot send OTP: user_id=%s has no email', user_id)
            return

        purpose_note = ''
        if purpose == 'phone_verify':
            purpose_note = '\nThis code was requested for phone verification.'

        send_email_logged(
            subject='Your verification code',
            message=(
                f'Your verification code is: {code}\n\n'
                f'The code is valid for {settings.OTP_CODE_TTL_MINUTES} minutes.'
                f'{purpose_note}\n'
                'If you did not request this code, please ignore this email.'
            ),
            recipient_list=[user.email],
            context=f'OTP purpose={purpose} user_id={user_id}',
        )
    except user_model.DoesNotExist:
        logger.warning('Cannot send OTP: user_id=%s does not exist', user_id)
    except Exception as exc:
        logger.exception('Failed to send OTP for user_id=%s', user_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, name='notifications.send_password_reset_email')
def send_password_reset_email(self, user_id, reset_url):
    """Send a password reset link to the user's email."""
    user_model = get_user_model()
    try:
        user = user_model.objects.get(pk=user_id)
        if not user.email:
            logger.warning('Cannot send password reset email: user_id=%s has no email', user_id)
            return

        ttl_hours = settings.PASSWORD_RESET_LINK_TTL_HOURS
        send_email_logged(
            subject='Восстановление пароля',
            message=(
                f'Здравствуйте, {user.full_name or user.email}.\n\n'
                'Мы получили запрос на восстановление пароля вашего аккаунта.\n'
                'Чтобы задать новый пароль, перейдите по ссылке:\n\n'
                f'{reset_url}\n\n'
                f'Ссылка действительна {ttl_hours} ч.\n'
                'Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо.'
            ),
            recipient_list=[user.email],
            context=f'password reset user_id={user_id}',
        )
    except user_model.DoesNotExist:
        logger.warning('Cannot send password reset email: user_id=%s does not exist', user_id)
    except Exception as exc:
        logger.exception('Failed to send password reset email for user_id=%s', user_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, name='notifications.send_admin_password_reset_email')
def send_admin_password_reset_email(self, user_id, new_password):
    """Send a newly generated password to the user after an admin reset."""
    user_model = get_user_model()
    try:
        user = user_model.objects.get(pk=user_id)
        if not user.email:
            logger.warning('Cannot send admin password reset email: user_id=%s has no email', user_id)
            return

        send_email_logged(
            subject='Ваш пароль был сброшен',
            message=(
                f'Здравствуйте, {user.full_name or user.email}.\n\n'
                'Администратор сбросил пароль вашего аккаунта.\n'
                f'Ваш новый пароль: {new_password}\n\n'
                'Рекомендуем войти и сменить пароль в личном кабинете.'
            ),
            recipient_list=[user.email],
            context=f'admin password reset user_id={user_id}',
        )
    except user_model.DoesNotExist:
        logger.warning('Cannot send admin password reset email: user_id=%s does not exist', user_id)
    except Exception as exc:
        logger.exception('Failed to send admin password reset email for user_id=%s', user_id)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_confirmation_email',
)
def send_order_confirmation_email(self, order_id):
    return _send_order_created(order_id, self)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_paid_notification',
)
def send_order_paid_notification(self, order_id):
    return _send_order_paid(order_id, self)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='notifications.send_order_status_update',
)
def send_order_status_update(self, order_id, new_status):
    return _send_order_status_changed(order_id, self, new_status=new_status)

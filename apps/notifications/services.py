from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User

from .models import Notification


class NotificationService:
    @classmethod
    def create_notification(
        cls,
        *,
        recipient=None,
        role=None,
        title='',
        message='',
        event_type=Notification.EventType.SYSTEM,
    ):
        if recipient is None and not role:
            raise ValidationError('recipient or role is required.')

        notification, _ = Notification.objects.get_or_create(
            recipient=recipient,
            role=role,
            title=title,
            message=message,
            event_type=event_type,
            is_read=False,
        )
        return notification

    @classmethod
    def notify_user(cls, user, title, message, event_type):
        return cls.create_notification(
            recipient=user,
            title=title,
            message=message,
            event_type=event_type,
        )

    @classmethod
    def notify_role(cls, role, title, message, event_type):
        return cls.create_notification(
            role=role,
            title=title,
            message=message,
            event_type=event_type,
        )

    @classmethod
    def notify_managers(cls, title, message, event_type):
        return [
            cls.notify_user(user, title, message, event_type)
            for user in cls.get_manager_recipients()
        ]

    @classmethod
    def notify_admins(cls, title, message, event_type):
        return [
            cls.notify_user(user, title, message, event_type)
            for user in cls.get_admin_recipients()
        ]

    @staticmethod
    def get_manager_recipients():
        user_model = get_user_model()
        return user_model.objects.filter(
            Q(role=User.Role.MANAGER)
            | (Q(is_staff=True) & Q(is_superuser=False) & ~Q(role=User.Role.ADMIN)),
            is_active=True,
        ).distinct()

    @staticmethod
    def get_admin_recipients():
        user_model = get_user_model()
        return user_model.objects.filter(
            Q(role=User.Role.ADMIN) | Q(is_superuser=True),
            is_active=True,
        ).distinct()


class EmailNotificationService:
    @classmethod
    def schedule_order_created_email(cls, order):
        from .tasks import send_order_created_email

        transaction.on_commit(lambda: send_order_created_email.delay(order.pk))

    @classmethod
    def schedule_order_paid_email(cls, order):
        from .tasks import send_order_paid_email

        transaction.on_commit(lambda: send_order_paid_email.delay(order.pk))

    @classmethod
    def schedule_order_status_changed_email(cls, order, old_status=None, new_status=None):
        from .tasks import send_order_status_changed_email

        transaction.on_commit(
            lambda: send_order_status_changed_email.delay(order.pk, old_status, new_status)
        )

    @classmethod
    def schedule_order_cancelled_email(cls, order):
        from .tasks import send_order_cancelled_email

        transaction.on_commit(lambda: send_order_cancelled_email.delay(order.pk))

    @classmethod
    def schedule_review_published_email(cls, review):
        from .tasks import send_review_published_email

        transaction.on_commit(lambda: send_review_published_email.delay(review.pk))

    @classmethod
    def schedule_review_rejected_email(cls, review):
        from .tasks import send_review_rejected_email

        transaction.on_commit(lambda: send_review_rejected_email.delay(review.pk))

    @classmethod
    def send_order_created_email(cls, order):
        subject = f'Ваш заказ #{order.order_number} принят'
        message = (
            f'Здравствуйте, {order.customer_name}.\n\n'
            f'Ваш заказ #{order.order_number} принят.\n'
            f'Сумма заказа: {order.total_amount} ₸\n'
            f'Статус заказа: {order.get_status_display()}\n'
        )
        return cls._send_customer_email(cls._order_recipient_email(order), subject, message)

    @classmethod
    def send_order_paid_email(cls, order):
        subject = f'Оплата подтверждена — заказ #{order.order_number}'
        message = (
            f'Ваш заказ #{order.order_number} успешно оплачен.\n'
            f'Сумма заказа: {order.total_amount} ₸\n'
            f'Статус оплаты: {order.get_payment_status_display()}\n'
        )
        return cls._send_customer_email(cls._order_recipient_email(order), subject, message)

    @classmethod
    def send_order_status_changed_email(cls, order, old_status=None, new_status=None):
        old_status = old_status or ''
        new_status = new_status or order.status
        subject = f'Статус заказа #{order.order_number} обновлён'
        message = (
            f'Статус заказа #{order.order_number} изменён.\n'
            f'Предыдущий статус: {cls._order_status_label(old_status)}\n'
            f'Новый статус: {cls._order_status_label(new_status)}\n'
        )
        return cls._send_customer_email(cls._order_recipient_email(order), subject, message)

    @classmethod
    def send_order_cancelled_email(cls, order):
        subject = f'Заказ #{order.order_number} отменён'
        message = (
            f'Ваш заказ #{order.order_number} отменён.\n'
            f'Статус заказа: {order.get_status_display()}\n'
            f'Статус оплаты: {order.get_payment_status_display()}\n'
        )
        return cls._send_customer_email(cls._order_recipient_email(order), subject, message)

    @classmethod
    def send_review_published_email(cls, review):
        subject = 'Ваш отзыв опубликован'
        message = (
            f'Ваш отзыв на товар "{review.product.name}" опубликован.\n'
            'Результат модерации: опубликован.\n'
        )
        if review.moderation_comment:
            message += f'Комментарий модератора: {review.moderation_comment}\n'
        return cls._send_customer_email(review.user.email, subject, message)

    @classmethod
    def send_review_rejected_email(cls, review):
        subject = 'Ваш отзыв отклонён'
        message = (
            f'Ваш отзыв на товар "{review.product.name}" отклонён.\n'
            'Результат модерации: отклонён.\n'
        )
        if review.moderation_comment:
            message += f'Комментарий модератора: {review.moderation_comment}\n'
        return cls._send_customer_email(review.user.email, subject, message)

    @staticmethod
    def _send_customer_email(recipient_email, subject, message):
        if not recipient_email:
            return 0
        return send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )

    @staticmethod
    def _order_recipient_email(order):
        return order.email or getattr(order.user, 'email', '')

    @staticmethod
    def _order_status_label(status):
        from apps.orders.models import Order

        return dict(Order.Status.choices).get(status, status or '—')

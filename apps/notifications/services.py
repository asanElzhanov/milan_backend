from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User

from .email import send_email_logged
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

    @classmethod
    def notify_staff(cls, title, message, event_type):
        notifications = []
        seen_user_ids = set()
        for user in list(cls.get_manager_recipients()) + list(cls.get_admin_recipients()):
            if user.pk in seen_user_ids:
                continue
            seen_user_ids.add(user.pk)
            notifications.append(cls.notify_user(user, title, message, event_type))
        return notifications

    @classmethod
    def notify_new_order(cls, order):
        return cls.notify_staff(
            title=f'Новый заказ #{order.order_number}',
            message=(
                f'Создан новый заказ #{order.order_number}.\n'
                f'Покупатель: {order.customer_name}\n'
                f'Сумма: {order.total_amount} ₸'
            ),
            event_type=Notification.EventType.ORDER_CREATED,
        )

    @classmethod
    def notify_payment_success(cls, order):
        return cls.notify_staff(
            title=f'Успешная оплата #{order.order_number}',
            message=(
                f'Оплата заказа #{order.order_number} прошла успешно.\n'
                f'Сумма: {order.total_amount} ₸\n'
                f'Статус оплаты: {order.get_payment_status_display()}'
            ),
            event_type=Notification.EventType.PAYMENT_SUCCESS,
        )

    @classmethod
    def notify_payment_error(cls, *, order=None, provider='', error_message=''):
        order_number = getattr(order, 'order_number', '') or 'неизвестен'
        safe_message = (error_message or 'Платёж не был завершён успешно.')[:300]
        provider_text = provider or 'unknown'
        return cls.notify_staff(
            title=f'Ошибка оплаты #{order_number}',
            message=(
                f'Ошибка оплаты заказа #{order_number}.\n'
                f'Провайдер: {provider_text}\n'
                f'Детали: {safe_message}'
            ),
            event_type=Notification.EventType.PAYMENT_ERROR,
        )

    @classmethod
    def notify_new_review(cls, review):
        return cls.notify_staff(
            title='Новый отзыв на модерации',
            message=(
                f'Новый отзыв на товар "{review.product.name_ru}".\n'
                f'Пользователь: {review.user.email}\n'
                f'Оценка: {review.rating}'
            ),
            event_type=Notification.EventType.REVIEW_CREATED,
        )

    @classmethod
    def notify_low_stock(cls, variant):
        threshold = getattr(settings, 'LOW_STOCK_THRESHOLD', 3)
        return cls.notify_staff(
            title=f'Низкий остаток: {variant.sku}',
            message=(
                f'Остаток варианта {variant.sku} ниже порога.\n'
                f'Товар: {variant.product.name_ru}\n'
                f'Текущий остаток: {variant.stock_quantity}\n'
                f'Порог: {threshold}'
            ),
            event_type=Notification.EventType.LOW_STOCK,
        )

    @classmethod
    def notify_import_error(cls, import_job, error_message=''):
        source = getattr(import_job.file, 'name', '') or f'Import #{import_job.pk}'
        safe_message = (error_message or import_job.error_message or 'Импорт завершился с ошибками.')[:300]
        return cls.notify_staff(
            title=f'Ошибка импорта #{import_job.pk}',
            message=(
                f'Импорт товаров завершился с ошибкой.\n'
                f'Источник: {source}\n'
                f'Создан: {import_job.created_at:%Y-%m-%d %H:%M:%S}\n'
                f'Детали: {safe_message}'
            ),
            event_type=Notification.EventType.IMPORT_ERROR,
        )

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
            f'Ваш отзыв на товар "{review.product.name_ru}" опубликован.\n'
            'Результат модерации: опубликован.\n'
        )
        if review.moderation_comment:
            message += f'Комментарий модератора: {review.moderation_comment}\n'
        return cls._send_customer_email(review.user.email, subject, message)

    @classmethod
    def send_review_rejected_email(cls, review):
        subject = 'Ваш отзыв отклонён'
        message = (
            f'Ваш отзыв на товар "{review.product.name_ru}" отклонён.\n'
            'Результат модерации: отклонён.\n'
        )
        if review.moderation_comment:
            message += f'Комментарий модератора: {review.moderation_comment}\n'
        return cls._send_customer_email(review.user.email, subject, message)

    @staticmethod
    def _send_customer_email(recipient_email, subject, message):
        if not recipient_email:
            return 0
        return send_email_logged(
            subject=subject,
            message=message,
            recipient_list=[recipient_email],
            context='customer notification',
        )

    @staticmethod
    def _order_recipient_email(order):
        return order.email or getattr(order.user, 'email', '')

    @staticmethod
    def _order_status_label(status):
        from apps.orders.models import Order

        return dict(Order.Status.choices).get(status, status or '—')

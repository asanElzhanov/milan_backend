from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
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

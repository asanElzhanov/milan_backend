from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(email='notify-customer@example.com')
        self.manager = User.objects.create_user(
            email='notify-manager@example.com',
            role=User.Role.MANAGER,
        )
        self.staff = User.objects.create_user(
            email='notify-staff@example.com',
            is_staff=True,
        )
        self.admin = User.objects.create_user(
            email='notify-admin@example.com',
            role=User.Role.ADMIN,
        )
        self.superuser = User.objects.create_superuser(
            email='notify-superuser@example.com',
            password='secret123',
        )

    def test_create_notification_creates_notification(self):
        notification = NotificationService.create_notification(
            recipient=self.customer,
            title='System notice',
            message='Hello',
            event_type=Notification.EventType.SYSTEM,
        )

        self.assertEqual(notification.recipient, self.customer)
        self.assertIsNone(notification.role)
        self.assertEqual(notification.title, 'System notice')
        self.assertEqual(notification.message, 'Hello')
        self.assertEqual(notification.event_type, Notification.EventType.SYSTEM)

    def test_create_notification_requires_recipient_or_role(self):
        with self.assertRaises(ValidationError):
            NotificationService.create_notification(
                title='No target',
                message='Missing recipient and role',
            )

    def test_notify_user_creates_notification_for_user(self):
        notification = NotificationService.notify_user(
            self.customer,
            'Order paid',
            'Your order was paid.',
            Notification.EventType.ORDER_PAID,
        )

        self.assertEqual(notification.recipient, self.customer)
        self.assertEqual(notification.event_type, Notification.EventType.ORDER_PAID)

    def test_notify_role_creates_role_based_notification(self):
        notification = NotificationService.notify_role(
            Notification.Role.MANAGER,
            'New order',
            'A new order was created.',
            Notification.EventType.ORDER_CREATED,
        )

        self.assertIsNone(notification.recipient)
        self.assertEqual(notification.role, Notification.Role.MANAGER)

    def test_notify_managers_resolves_manager_and_staff_users(self):
        inactive_manager = User.objects.create_user(
            email='inactive-manager@example.com',
            role=User.Role.MANAGER,
            is_active=False,
        )

        notifications = NotificationService.notify_managers(
            'Low stock',
            'A product variant is low on stock.',
            Notification.EventType.LOW_STOCK,
        )

        recipients = {notification.recipient for notification in notifications}
        self.assertIn(self.manager, recipients)
        self.assertIn(self.staff, recipients)
        self.assertNotIn(self.customer, recipients)
        self.assertNotIn(self.admin, recipients)
        self.assertNotIn(self.superuser, recipients)
        self.assertNotIn(inactive_manager, recipients)

    def test_notify_admins_resolves_admin_and_superuser_users(self):
        inactive_admin = User.objects.create_user(
            email='inactive-admin@example.com',
            role=User.Role.ADMIN,
            is_active=False,
        )

        notifications = NotificationService.notify_admins(
            'Payment error',
            'Payment failed.',
            Notification.EventType.PAYMENT_ERROR,
        )

        recipients = {notification.recipient for notification in notifications}
        self.assertIn(self.admin, recipients)
        self.assertIn(self.superuser, recipients)
        self.assertNotIn(self.customer, recipients)
        self.assertNotIn(self.manager, recipients)
        self.assertNotIn(self.staff, recipients)
        self.assertNotIn(inactive_admin, recipients)

    def test_is_read_defaults_to_false(self):
        notification = NotificationService.notify_user(
            self.customer,
            'Unread',
            'This should be unread.',
            Notification.EventType.SYSTEM,
        )

        self.assertFalse(notification.is_read)

    def test_notification_ordering_is_newest_first(self):
        first = NotificationService.notify_user(
            self.customer,
            'First',
            'First message',
            Notification.EventType.SYSTEM,
        )
        second = NotificationService.notify_user(
            self.customer,
            'Second',
            'Second message',
            Notification.EventType.SYSTEM,
        )
        Notification.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        Notification.objects.filter(pk=second.pk).update(created_at=timezone.now())

        self.assertEqual(list(Notification.objects.all()), [second, first])

    def test_exact_duplicate_unread_notification_is_not_created_twice(self):
        first = NotificationService.notify_user(
            self.customer,
            'Same title',
            'Same message',
            Notification.EventType.SYSTEM,
        )
        second = NotificationService.notify_user(
            self.customer,
            'Same title',
            'Same message',
            Notification.EventType.SYSTEM,
        )

        self.assertEqual(first, second)
        self.assertEqual(Notification.objects.count(), 1)

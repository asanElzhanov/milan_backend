from django.contrib import admin
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.notifications.admin import NotificationAdmin
from apps.notifications.models import Notification


class NotificationAdminTests(TestCase):
    def setUp(self):
        self.site = admin.AdminSite()
        self.model_admin = NotificationAdmin(Notification, self.site)
        self.request = RequestFactory().get('/django-admin/notifications/notification/')
        self.request.user = User.objects.create_superuser(
            email='notification-admin@example.com',
            password='secret123',
        )

    def test_admin_list_configuration(self):
        self.assertEqual(
            self.model_admin.list_display,
            ('title', 'recipient', 'role', 'event_type', 'is_read', 'created_at'),
        )
        self.assertEqual(
            self.model_admin.list_filter,
            ('event_type', 'role', 'is_read', 'created_at'),
        )
        self.assertIn('recipient__email', self.model_admin.search_fields)
        self.assertIn('title', self.model_admin.readonly_fields)
        self.assertEqual(self.model_admin.ordering, ('-created_at',))

    def test_admin_does_not_allow_manual_add(self):
        self.assertFalse(self.model_admin.has_add_permission(self.request))

    def test_admin_actions_mark_read_and_unread(self):
        user = User.objects.create_user(email='notification-admin-user@example.com')
        notification = Notification.objects.create(
            recipient=user,
            title='Admin action',
            message='Admin action message',
            event_type=Notification.EventType.SYSTEM,
        )

        self.model_admin.mark_read(self.request, Notification.objects.filter(pk=notification.pk))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        self.model_admin.mark_unread(self.request, Notification.objects.filter(pk=notification.pk))
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

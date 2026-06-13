from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='notification-api@example.com')
        self.other_user = User.objects.create_user(email='other-notification-api@example.com')
        self.manager = User.objects.create_user(
            email='manager-notification-api@example.com',
            role=User.Role.MANAGER,
        )
        self.own_notification = NotificationService.notify_user(
            self.user,
            'Own notification',
            'Visible only to owner',
            Notification.EventType.SYSTEM,
        )
        self.other_notification = NotificationService.notify_user(
            self.other_user,
            'Other notification',
            'Hidden from current user',
            Notification.EventType.SYSTEM,
        )
        self.order_notification = NotificationService.notify_user(
            self.user,
            'Order notification',
            'Order was created',
            Notification.EventType.ORDER_CREATED,
        )
        self.read_notification = NotificationService.notify_user(
            self.user,
            'Read notification',
            'Already read',
            Notification.EventType.PAYMENT_SUCCESS,
        )
        self.read_notification.is_read = True
        self.read_notification.save(update_fields=['is_read', 'updated_at'])
        self.role_notification = NotificationService.notify_role(
            Notification.Role.MANAGER,
            'Role notification',
            'Manager-only message',
            Notification.EventType.IMPORT_ERROR,
        )

    def list_url(self):
        return '/api/v1/notifications/'

    def mark_read_url(self, notification):
        return f'/api/v1/notifications/{notification.pk}/mark-read/'

    def mark_all_read_url(self):
        return '/api/v1/notifications/mark-all-read/'

    def response_results(self, response):
        if isinstance(response.data, dict) and 'results' in response.data:
            return response.data['results']
        return response.data

    def test_user_sees_own_notifications(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item['id'] for item in self.response_results(response)}
        self.assertIn(self.own_notification.id, ids)
        self.assertIn(self.order_notification.id, ids)
        self.assertIn(self.read_notification.id, ids)

    def test_user_does_not_see_another_users_notifications_or_role_notifications(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.list_url())

        ids = {item['id'] for item in self.response_results(response)}
        self.assertNotIn(self.other_notification.id, ids)
        self.assertNotIn(self.role_notification.id, ids)

    def test_manager_does_not_see_role_based_notifications_in_user_endpoint(self):
        self.client.force_authenticate(user=self.manager)

        response = self.client.get(self.list_url())

        ids = {item['id'] for item in self.response_results(response)}
        self.assertNotIn(self.role_notification.id, ids)

    def test_response_fields(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.list_url())

        item = self.response_results(response)[0]
        self.assertEqual(
            set(item.keys()),
            {'id', 'title', 'message', 'event_type', 'is_read', 'created_at'},
        )

    def test_user_can_mark_own_notification_as_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.mark_read_url(self.own_notification))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.own_notification.refresh_from_db()
        self.assertTrue(self.own_notification.is_read)

    def test_user_cannot_mark_another_users_notification_as_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.mark_read_url(self.other_notification))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_mark_all_read_updates_only_current_user_notifications(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.mark_all_read_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.filter(recipient=self.user, is_read=False).exists())
        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_is_read_filter_works(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.list_url(), {'is_read': 'true'})

        ids = {item['id'] for item in self.response_results(response)}
        self.assertIn(self.read_notification.id, ids)
        self.assertNotIn(self.own_notification.id, ids)

    def test_event_type_filter_works(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.list_url(),
            {'event_type': Notification.EventType.ORDER_CREATED},
        )

        ids = {item['id'] for item in self.response_results(response)}
        self.assertEqual(ids, {self.order_notification.id})

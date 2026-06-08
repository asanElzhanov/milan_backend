from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User


class ProfileAPITests(APITestCase):
    url = '/api/v1/auth/me/'

    def setUp(self):
        self.user = User.objects.create_user(
            email='profile@example.com',
            password='secret123',
            first_name='Old',
            last_name='Name',
            phone='+77000000011',
        )

    def test_authenticated_user_can_get_profile(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertEqual(response.data['role'], User.Role.CUSTOMER)
        self.assertIn('full_name', response.data)
        self.assertIn('is_verified', response.data)

    def test_anonymous_user_cannot_get_profile(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_update_profile_fields(self):
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.url, {
            'first_name': 'Ali',
            'last_name': 'Khan',
            'phone': '+77000000012',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ali')
        self.assertEqual(self.user.last_name, 'Khan')
        self.assertEqual(str(self.user.phone), '+77000000012')

    def test_user_cannot_update_role_or_privilege_flags(self):
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.url, {
            'role': User.Role.ADMIN,
            'is_staff': True,
            'is_superuser': True,
            'is_email_verified': True,
            'is_verified': True,
            'first_name': 'Safe',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.CUSTOMER)
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.is_email_verified)
        self.assertEqual(self.user.first_name, 'Safe')

    def test_profile_response_does_not_expose_sensitive_fields(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('password', response.data)
        self.assertNotIn('groups', response.data)
        self.assertNotIn('user_permissions', response.data)
        self.assertNotIn('is_superuser', response.data)

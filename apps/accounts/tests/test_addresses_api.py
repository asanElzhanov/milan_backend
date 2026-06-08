from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Address, User


class AddressAPITests(APITestCase):
    list_url = '/api/v1/auth/addresses/'

    def setUp(self):
        self.user = User.objects.create_user(email='address@example.com', password='secret123')
        self.other_user = User.objects.create_user(email='other-address@example.com', password='secret123')

    def detail_url(self, address):
        return f'/api/v1/auth/addresses/{address.id}/'

    def address_payload(self, **overrides):
        payload = {
            'title': 'Home',
            'country': 'Kazakhstan',
            'city': 'Almaty',
            'street': 'Abay 1',
            'apartment': '10',
            'postal_code': '050000',
            'is_default': False,
        }
        payload.update(overrides)
        return payload

    def test_anonymous_user_cannot_access_addresses(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_create_first_default_address(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, self.address_payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = Address.objects.get(user=self.user)
        self.assertTrue(address.is_default)
        self.assertIn('created_at', response.data)
        self.assertIn('updated_at', response.data)
        self.assertNotIn('user', response.data)

    def test_create_address_ignores_user_from_body(self):
        self.client.force_authenticate(self.user)
        payload = self.address_payload(user=self.other_user.id)

        response = self.client.post(self.list_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Address.objects.get().user, self.user)

    def test_user_sees_only_own_addresses_ordered_default_then_newest(self):
        old = Address.objects.create(user=self.user, title='Old', city='Almaty', street='Old 1')
        default = Address.objects.create(user=self.user, title='Default', city='Astana', street='Default 1', is_default=True)
        newest = Address.objects.create(user=self.user, title='Newest', city='Shymkent', street='Newest 1')
        Address.objects.create(user=self.other_user, title='Other', city='Other', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in response.data['results']] if isinstance(response.data, dict) else [item['id'] for item in response.data]
        self.assertEqual(ids, [default.id, newest.id, old.id])

    def test_setting_default_address_unsets_other_defaults_for_same_user_only(self):
        first = Address.objects.create(user=self.user, title='First', city='Almaty', street='First 1')
        second = Address.objects.create(user=self.user, title='Second', city='Astana', street='Second 1')
        other_default = Address.objects.create(user=self.other_user, title='Other', city='Other', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.detail_url(second), {'is_default': True}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        other_default.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertTrue(other_default.is_default)

    def test_user_cannot_get_patch_or_delete_other_users_address(self):
        other_address = Address.objects.create(user=self.other_user, title='Other', city='Other', street='Other 1')
        self.client.force_authenticate(self.user)

        get_response = self.client.get(self.detail_url(other_address))
        patch_response = self.client.patch(self.detail_url(other_address), {'city': 'Hack'}, format='json')
        delete_response = self.client.delete(self.detail_url(other_address))

        self.assertEqual(get_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(patch_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)
        other_address.refresh_from_db()
        self.assertEqual(other_address.city, 'Other')

    def test_deleting_default_address_assigns_latest_remaining_address_as_default(self):
        default = Address.objects.create(user=self.user, title='Default', city='Almaty', street='Default 1')
        old = Address.objects.create(user=self.user, title='Old', city='Astana', street='Old 1')
        latest = Address.objects.create(user=self.user, title='Latest', city='Shymkent', street='Latest 1')
        default.is_default = True
        default.save(update_fields=['is_default', 'updated_at'])
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(default))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(pk=default.pk).exists())
        old.refresh_from_db()
        latest.refresh_from_db()
        self.assertFalse(old.is_default)
        self.assertTrue(latest.is_default)

    def test_deleting_only_default_address_leaves_no_addresses(self):
        default = Address.objects.create(user=self.user, title='Default', city='Almaty', street='Default 1')
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(default))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(user=self.user).exists())

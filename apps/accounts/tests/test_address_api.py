from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Address, User


class AddressAPITests(APITestCase):
    list_url = '/api/v1/auth/addresses/'

    def setUp(self):
        self.user = User.objects.create_user(email='address-api@example.com', password='secret123')
        self.other_user = User.objects.create_user(email='other-address-api@example.com', password='secret123')

    def detail_url(self, address):
        return f'/api/v1/auth/addresses/{address.id}/'

    def payload(self, **overrides):
        data = {
            'title': 'Home',
            'country': 'Kazakhstan',
            'city': 'Almaty',
            'street': 'Abay 1',
            'apartment': '10',
            'postal_code': '050000',
            'is_default': False,
        }
        data.update(overrides)
        return data

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_anonymous_user_cannot_get_address_list(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_get_only_own_addresses(self):
        own = Address.objects.create(user=self.user, title='Own', city='Almaty', street='Own 1')
        Address.objects.create(user=self.other_user, title='Other', city='Astana', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], own.id)
        self.assertNotIn('user', items[0])

    def test_address_list_orders_default_first_then_newest(self):
        old = Address.objects.create(user=self.user, title='Old', city='Almaty', street='Old 1')
        default = Address.objects.create(user=self.user, title='Default', city='Astana', street='Default 1', is_default=True)
        newest = Address.objects.create(user=self.user, title='Newest', city='Shymkent', street='Newest 1')
        self.client.force_authenticate(self.user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item['id'] for item in self.response_items(response)]
        self.assertEqual(ids, [default.id, newest.id, old.id])

    def test_user_can_create_address_bound_to_request_user(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = Address.objects.get()
        self.assertEqual(address.user, self.user)
        self.assertTrue(address.is_default)
        self.assertNotIn('user', response.data)
        self.assertIn('created_at', response.data)
        self.assertIn('updated_at', response.data)

    def test_user_field_in_create_body_is_ignored(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, self.payload(user=self.other_user.id), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Address.objects.get().user, self.user)

    def test_second_address_without_default_keeps_first_default(self):
        first = Address.objects.create(user=self.user, title='First', city='Almaty', street='First 1')
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, self.payload(title='Second', street='Second 2'), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first.refresh_from_db()
        second = Address.objects.get(pk=response.data['id'])
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

    def test_second_address_with_default_unsets_first_default(self):
        first = Address.objects.create(user=self.user, title='First', city='Almaty', street='First 1')
        self.client.force_authenticate(self.user)

        response = self.client.post(
            self.list_url,
            self.payload(title='Second', street='Second 2', is_default=True),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        first.refresh_from_db()
        second = Address.objects.get(pk=response.data['id'])
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_user_can_get_detail_for_own_address(self):
        address = Address.objects.create(user=self.user, title='Home', city='Almaty', street='Abay 1')
        self.client.force_authenticate(self.user)

        response = self.client.get(self.detail_url(address))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], address.id)
        self.assertEqual(response.data['city'], 'Almaty')
        self.assertNotIn('user', response.data)

    def test_user_cannot_get_foreign_address(self):
        address = Address.objects.create(user=self.other_user, title='Other', city='Astana', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.get(self.detail_url(address))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn('city', getattr(response, 'data', {}))

    def test_user_can_update_own_address(self):
        address = Address.objects.create(user=self.user, title='Home', city='Almaty', street='Abay 1')
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.detail_url(address), {'city': 'Astana'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertEqual(address.city, 'Astana')

    def test_user_cannot_update_foreign_address(self):
        address = Address.objects.create(user=self.other_user, title='Other', city='Astana', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.detail_url(address), {'city': 'Hack'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        address.refresh_from_db()
        self.assertEqual(address.city, 'Astana')

    def test_user_field_in_patch_body_is_ignored(self):
        address = Address.objects.create(user=self.user, title='Home', city='Almaty', street='Abay 1')
        self.client.force_authenticate(self.user)

        response = self.client.patch(self.detail_url(address), {'user': self.other_user.id, 'city': 'Astana'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertEqual(address.user, self.user)
        self.assertEqual(address.city, 'Astana')

    def test_user_can_delete_own_address(self):
        address = Address.objects.create(user=self.user, title='Home', city='Almaty', street='Abay 1')
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(address))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(pk=address.pk).exists())

    def test_user_cannot_delete_foreign_address(self):
        address = Address.objects.create(user=self.other_user, title='Other', city='Astana', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(address))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Address.objects.filter(pk=address.pk).exists())

    def test_deleting_non_default_address_does_not_change_default(self):
        default = Address.objects.create(user=self.user, title='Default', city='Almaty', street='Default 1')
        other = Address.objects.create(user=self.user, title='Other', city='Astana', street='Other 1')
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(other))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        default.refresh_from_db()
        self.assertTrue(default.is_default)
        self.assertFalse(Address.objects.filter(pk=other.pk).exists())

    def test_deleting_default_address_assigns_one_remaining_default(self):
        default = Address.objects.create(user=self.user, title='Default', city='Almaty', street='Default 1')
        old = Address.objects.create(user=self.user, title='Old', city='Astana', street='Old 1')
        latest = Address.objects.create(user=self.user, title='Latest', city='Shymkent', street='Latest 1')
        default.is_default = True
        default.save(update_fields=['is_default', 'updated_at'])
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(default))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        old.refresh_from_db()
        latest.refresh_from_db()
        self.assertFalse(old.is_default)
        self.assertTrue(latest.is_default)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_deleting_only_default_address_succeeds(self):
        default = Address.objects.create(user=self.user, title='Default', city='Almaty', street='Default 1')
        self.client.force_authenticate(self.user)

        response = self.client.delete(self.detail_url(default))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(user=self.user).exists())

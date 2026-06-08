from django.test import TestCase

from apps.accounts.models import Address, User


class AddressModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='address-model@example.com', password='secret123')
        self.other_user = User.objects.create_user(email='other-address-model@example.com', password='secret123')

    def create_address(self, user=None, **overrides):
        data = {
            'user': user or self.user,
            'title': 'Home',
            'country': 'Kazakhstan',
            'city': 'Almaty',
            'street': 'Abay 1',
            'apartment': '10',
            'postal_code': '050000',
        }
        data.update(overrides)
        return Address.objects.create(**data)

    def test_create_address(self):
        address = self.create_address()

        self.assertEqual(address.user, self.user)
        self.assertEqual(address.title, 'Home')
        self.assertEqual(address.country, 'Kazakhstan')
        self.assertEqual(address.city, 'Almaty')
        self.assertEqual(address.street, 'Abay 1')
        self.assertEqual(address.apartment, '10')
        self.assertEqual(address.postal_code, '050000')

    def test_str_returns_readable_value_with_title(self):
        address = self.create_address(title='Work', city='Astana', street='Main 5')

        self.assertEqual(str(address), 'Work - Astana, Main 5')

    def test_str_returns_readable_value_without_title(self):
        address = self.create_address(title='', city='Astana', street='Main 5')

        self.assertEqual(str(address), 'Astana, Main 5')

    def test_first_address_becomes_default(self):
        address = self.create_address(is_default=False)

        self.assertTrue(address.is_default)

    def test_second_address_without_default_does_not_replace_existing_default(self):
        first = self.create_address()
        second = self.create_address(title='Second', street='Second 2', is_default=False)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_default)
        self.assertFalse(second.is_default)

    def test_second_address_with_default_unsets_first_default(self):
        first = self.create_address()
        second = self.create_address(title='Second', street='Second 2', is_default=True)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_updating_address_to_default_unsets_other_defaults_for_same_user(self):
        first = self.create_address()
        second = self.create_address(title='Second', street='Second 2')

        second.is_default = True
        second.save()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)

    def test_default_logic_is_scoped_to_one_user(self):
        first = self.create_address()
        other_first = self.create_address(user=self.other_user, title='Other', street='Other 1')
        second = self.create_address(title='Second', street='Second 2', is_default=True)

        first.refresh_from_db()
        second.refresh_from_db()
        other_first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(second.is_default)
        self.assertTrue(other_first.is_default)

    def test_addresses_for_different_users_do_not_affect_each_other(self):
        user_address = self.create_address()
        other_address = self.create_address(user=self.other_user, title='Other', street='Other 1')

        user_address.refresh_from_db()
        other_address.refresh_from_db()
        self.assertTrue(user_address.is_default)
        self.assertTrue(other_address.is_default)

    def test_user_cannot_have_two_default_addresses_after_saves(self):
        first = self.create_address()
        second = self.create_address(title='Second', street='Second 2')
        third = self.create_address(title='Third', street='Third 3', is_default=True)

        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertTrue(third.is_default)
        self.assertFalse(first.is_default)
        self.assertFalse(second.is_default)

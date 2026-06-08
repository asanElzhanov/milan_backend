from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User


class UserModelTests(TestCase):
    def test_create_user_defaults(self):
        user = User.objects.create_user(email='User@EXAMPLE.COM', password='secret123')

        self.assertEqual(user.email, 'User@example.com')
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password('secret123'))
        self.assertNotEqual(user.password, 'secret123')

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='secret123')

    def test_create_superuser_defaults(self):
        user = User.objects.create_superuser(email='admin@example.com', password='secret123')

        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_create_superuser_rejects_invalid_staff_flags(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='admin1@example.com',
                password='secret123',
                is_staff=False,
            )
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email='admin2@example.com',
                password='secret123',
                is_superuser=False,
            )

    def test_full_name_property(self):
        user = User(first_name='Ali', last_name='Khan')
        self.assertEqual(user.full_name, 'Ali Khan')

        user = User(first_name='Ali', last_name='')
        self.assertEqual(user.full_name, 'Ali')

        user = User(first_name='', last_name='Khan')
        self.assertEqual(user.full_name, 'Khan')

        user = User(first_name='', last_name='')
        self.assertEqual(user.full_name, '')

    def test_is_verified_property(self):
        user = User(is_email_verified=True)
        self.assertTrue(user.is_verified)

    def test_duplicate_email_is_not_allowed(self):
        User.objects.create_user(email='duplicate@example.com', password='secret123')
        with self.assertRaises(IntegrityError):
            User.objects.create_user(email='duplicate@example.com', password='secret123')

    def test_duplicate_phone_is_not_allowed_when_present(self):
        User.objects.create_user(
            email='phone1@example.com',
            phone='+77000000001',
            password='secret123',
        )
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email='phone2@example.com',
                phone='+77000000001',
                password='secret123',
            )

    def test_users_without_phone_are_allowed(self):
        User.objects.create_user(email='no-phone1@example.com', password='secret123')
        User.objects.create_user(email='no-phone2@example.com', password='secret123')
        self.assertEqual(User.objects.count(), 2)

    def test_role_properties(self):
        customer = User(role=User.Role.CUSTOMER)
        manager = User(role=User.Role.MANAGER)
        admin = User(role=User.Role.ADMIN)

        self.assertTrue(customer.is_customer)
        self.assertFalse(customer.is_manager)
        self.assertFalse(customer.is_admin_role)
        self.assertFalse(manager.is_customer)
        self.assertTrue(manager.is_manager)
        self.assertFalse(manager.is_admin_role)
        self.assertFalse(admin.is_customer)
        self.assertFalse(admin.is_manager)
        self.assertTrue(admin.is_admin_role)

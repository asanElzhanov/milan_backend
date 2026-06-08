from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.accounts.permissions import (
    IsAdminRole,
    IsCustomer,
    IsManager,
    IsManagerOrAdmin,
    IsOwnerOrManagerOrAdmin,
)


class ObjectWithUser:
    def __init__(self, user):
        self.user = user


class ObjectWithOwner:
    def __init__(self, owner):
        self.owner = owner


class ObjectWithoutOwner:
    pass


class PermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.customer = User.objects.create_user('customer@example.com', 'secret123')
        self.other_customer = User.objects.create_user('other@example.com', 'secret123')
        self.manager = User.objects.create_user(
            'manager@example.com',
            'secret123',
            role=User.Role.MANAGER,
        )
        self.admin = User.objects.create_user(
            'admin@example.com',
            'secret123',
            role=User.Role.ADMIN,
        )
        self.superuser = User.objects.create_superuser('super@example.com', 'secret123')

    def request_for(self, user):
        request = self.factory.get('/')
        request.user = user
        return request

    def test_anonymous_fails_role_permissions(self):
        request = self.request_for(AnonymousUser())

        self.assertFalse(IsCustomer().has_permission(request, None))
        self.assertFalse(IsManager().has_permission(request, None))
        self.assertFalse(IsAdminRole().has_permission(request, None))
        self.assertFalse(IsManagerOrAdmin().has_permission(request, None))
        self.assertFalse(IsOwnerOrManagerOrAdmin().has_permission(request, None))

    def test_customer_permissions(self):
        request = self.request_for(self.customer)

        self.assertTrue(IsCustomer().has_permission(request, None))
        self.assertFalse(IsManager().has_permission(request, None))
        self.assertFalse(IsAdminRole().has_permission(request, None))

    def test_manager_permissions(self):
        request = self.request_for(self.manager)

        self.assertTrue(IsManager().has_permission(request, None))
        self.assertTrue(IsManagerOrAdmin().has_permission(request, None))

    def test_admin_permissions(self):
        request = self.request_for(self.admin)

        self.assertTrue(IsAdminRole().has_permission(request, None))
        self.assertTrue(IsManagerOrAdmin().has_permission(request, None))

    def test_superuser_permissions(self):
        request = self.request_for(self.superuser)

        self.assertTrue(IsAdminRole().has_permission(request, None))
        self.assertTrue(IsManagerOrAdmin().has_permission(request, None))

    def test_owner_object_permission(self):
        permission = IsOwnerOrManagerOrAdmin()
        request = self.request_for(self.customer)

        self.assertTrue(permission.has_object_permission(request, None, self.customer))
        self.assertTrue(permission.has_object_permission(request, None, ObjectWithUser(self.customer)))
        self.assertTrue(permission.has_object_permission(request, None, ObjectWithOwner(self.customer)))

    def test_other_customer_cannot_access_foreign_object(self):
        permission = IsOwnerOrManagerOrAdmin()
        request = self.request_for(self.other_customer)

        self.assertFalse(permission.has_object_permission(request, None, ObjectWithUser(self.customer)))
        self.assertFalse(permission.has_object_permission(request, None, ObjectWithOwner(self.customer)))
        self.assertFalse(permission.has_object_permission(request, None, ObjectWithoutOwner()))

    def test_manager_admin_superuser_can_access_object(self):
        permission = IsOwnerOrManagerOrAdmin()
        obj = ObjectWithoutOwner()

        self.assertTrue(permission.has_object_permission(self.request_for(self.manager), None, obj))
        self.assertTrue(permission.has_object_permission(self.request_for(self.admin), None, obj))
        self.assertTrue(permission.has_object_permission(self.request_for(self.superuser), None, obj))

    def test_anonymous_object_permission_is_safe(self):
        permission = IsOwnerOrManagerOrAdmin()
        request = self.request_for(AnonymousUser())

        self.assertFalse(permission.has_object_permission(request, None, ObjectWithoutOwner()))

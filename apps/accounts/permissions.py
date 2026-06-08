from rest_framework import permissions

from .models import User


def _is_authenticated(user):
    return bool(user and user.is_authenticated)


def _has_role(user, role):
    return _is_authenticated(user) and getattr(user, 'role', None) == role


class IsCustomer(permissions.BasePermission):
    def has_permission(self, request, view):
        return _has_role(request.user, User.Role.CUSTOMER)


class IsManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return _has_role(request.user, User.Role.MANAGER)


class IsAdminRole(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return _is_authenticated(user) and (
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) == User.Role.ADMIN
        )


class IsManagerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return _is_authenticated(user) and (
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) in {User.Role.MANAGER, User.Role.ADMIN}
        )


class IsOwnerOrManagerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return _is_authenticated(request.user)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not _is_authenticated(user):
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if getattr(user, 'role', None) in {User.Role.MANAGER, User.Role.ADMIN}:
            return True
        if obj == user:
            return True
        owner = getattr(obj, 'user', None)
        if owner == user:
            return True
        owner = getattr(obj, 'owner', None)
        return owner == user

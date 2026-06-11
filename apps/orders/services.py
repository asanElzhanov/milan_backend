from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import ProductVariant
from apps.catalog.services import StockService

from .models import Cart, CartItem


class CartError(ValidationError):
    pass


class CartNotFoundError(CartError):
    pass


class InvalidCartQuantityError(CartError):
    pass


class NotEnoughStockError(CartError):
    pass


class InactiveVariantError(CartError):
    pass


class CartService:
    @classmethod
    def get_or_create_guest_cart(cls, token=None):
        if token:
            token = cls._resolve_token(token)
            try:
                return Cart.objects.get(token=token, user__isnull=True, is_active=True)
            except Cart.DoesNotExist as exc:
                raise CartNotFoundError('Гостевая корзина не найдена.') from exc

        return Cart.objects.create(user=None, is_active=True)

    @classmethod
    def get_or_create_user_cart(cls, user):
        if not user or not user.is_authenticated:
            raise CartNotFoundError('Пользователь не авторизован.')
        cart, _ = Cart.objects.get_or_create(
            user=user,
            is_active=True,
            defaults={'token': None},
        )
        return cart

    @classmethod
    def add_item(cls, cart, variant, quantity):
        quantity = cls._validate_quantity(quantity)
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            variant = cls._lock_variant(variant)
            cls._ensure_variant_available(variant)

            item = (
                CartItem.objects.select_for_update()
                .filter(cart=cart, variant=variant)
                .first()
            )
            new_quantity = quantity if item is None else item.quantity + quantity
            cls._ensure_stock_available(variant, new_quantity)

            if item is None:
                item = CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
            else:
                item.quantity = new_quantity
                item.save(update_fields=['quantity', 'updated_at'])
            return item, cart

    @classmethod
    def update_item(cls, cart, item_or_variant, quantity):
        quantity = cls._validate_quantity(quantity)
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item(cart, item_or_variant)
            variant = cls._lock_variant(item.variant_id)
            cls._ensure_variant_available(variant)
            cls._ensure_stock_available(variant, quantity)

            item.quantity = quantity
            item.save(update_fields=['quantity', 'updated_at'])
            return item, cart

    @classmethod
    def update_item_by_id(cls, cart, item_id, quantity):
        quantity = cls._validate_quantity(quantity)
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item_by_id(cart, item_id)
            variant = cls._lock_variant(item.variant_id)
            cls._ensure_variant_available(variant)
            cls._ensure_stock_available(variant, quantity)

            item.quantity = quantity
            item.save(update_fields=['quantity', 'updated_at'])
            return item, cart

    @classmethod
    def remove_item(cls, cart, item_or_variant):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item(cart, item_or_variant)
            item.delete()
            return cart

    @classmethod
    def remove_item_by_id(cls, cart, item_id):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item_by_id(cart, item_id)
            item.delete()
            return cart

    @classmethod
    def clear_cart(cls, cart):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            cart.items.select_for_update().delete()
            return cart

    @classmethod
    def recalculate_cart(cls, cart):
        prefetched_items = getattr(cart, '_prefetched_objects_cache', {}).get('items')
        if prefetched_items is not None:
            items = list(prefetched_items)
        else:
            items = list(
                cart.items.select_related('variant__product')
                .order_by('id')
            )
        total_quantity = sum(item.quantity for item in items)
        subtotal = sum(
            cls.get_effective_price(item.variant) * item.quantity
            for item in items
        )
        subtotal = subtotal or Decimal('0.00')
        return {
            'items_count': len(items),
            'total_quantity': total_quantity,
            'subtotal': subtotal,
            'total': subtotal,
        }

    @classmethod
    def merge_guest_cart_to_user_cart(cls, guest_token, user):
        token = cls._resolve_token(guest_token)
        with transaction.atomic():
            try:
                guest_cart = Cart.objects.select_for_update().get(
                    token=token,
                    user__isnull=True,
                    is_active=True,
                )
            except Cart.DoesNotExist as exc:
                raise CartNotFoundError('Гостевая корзина не найдена.') from exc

            user_cart = cls.get_or_create_user_cart(user)
            user_cart = cls._lock_cart(user_cart)

            guest_items = list(
                CartItem.objects.select_for_update()
                .filter(cart=guest_cart)
                .select_related('variant__product')
                .order_by('id')
            )
            for guest_item in guest_items:
                variant = cls._lock_variant(guest_item.variant_id)
                cls._ensure_variant_available(variant)
                user_item = (
                    CartItem.objects.select_for_update()
                    .filter(cart=user_cart, variant=variant)
                    .first()
                )
                new_quantity = guest_item.quantity
                if user_item is not None:
                    new_quantity += user_item.quantity
                cls._ensure_stock_available(variant, new_quantity)

            for guest_item in guest_items:
                user_item = (
                    CartItem.objects.select_for_update()
                    .filter(cart=user_cart, variant_id=guest_item.variant_id)
                    .first()
                )
                if user_item is None:
                    CartItem.objects.create(
                        cart=user_cart,
                        variant_id=guest_item.variant_id,
                        quantity=guest_item.quantity,
                    )
                else:
                    user_item.quantity += guest_item.quantity
                    user_item.save(update_fields=['quantity', 'updated_at'])

            guest_cart.items.all().delete()
            guest_cart.is_active = False
            guest_cart.save(update_fields=['is_active', 'updated_at'])
            return user_cart

    @staticmethod
    def get_effective_price(variant):
        return variant.variant_price if variant.variant_price is not None else variant.product.price

    @classmethod
    def _lock_cart(cls, cart):
        cart_id = cart.pk if isinstance(cart, Cart) else cart
        try:
            return Cart.objects.select_for_update().get(pk=cart_id)
        except Cart.DoesNotExist as exc:
            raise CartNotFoundError('Корзина не найдена.') from exc

    @classmethod
    def _lock_variant(cls, variant):
        variant_id = variant.pk if isinstance(variant, ProductVariant) else variant
        try:
            return ProductVariant.objects.select_for_update().select_related('product').get(pk=variant_id)
        except ProductVariant.DoesNotExist as exc:
            raise CartNotFoundError('Вариант товара не найден.') from exc

    @classmethod
    def _lock_item(cls, cart, item_or_variant):
        queryset = CartItem.objects.select_for_update().filter(cart=cart)
        if isinstance(item_or_variant, CartItem):
            item = queryset.filter(pk=item_or_variant.pk).first()
        elif isinstance(item_or_variant, ProductVariant):
            item = queryset.filter(variant=item_or_variant).first()
        else:
            item = queryset.filter(pk=item_or_variant).first()
            if item is None:
                item = queryset.filter(variant_id=item_or_variant).first()
        if item is None:
            raise CartNotFoundError('Позиция корзины не найдена.')
        return item

    @staticmethod
    def _lock_item_by_id(cart, item_id):
        item = CartItem.objects.select_for_update().filter(cart=cart, pk=item_id).first()
        if item is None:
            raise CartNotFoundError('Позиция корзины не найдена.')
        return item

    @staticmethod
    def _resolve_token(token):
        try:
            return uuid.UUID(str(token))
        except (TypeError, ValueError) as exc:
            raise CartNotFoundError('Некорректный token корзины.') from exc

    @staticmethod
    def _validate_quantity(quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise InvalidCartQuantityError('Количество должно быть положительным числом.') from exc
        if quantity <= 0:
            raise InvalidCartQuantityError('Количество должно быть больше нуля.')
        return quantity

    @staticmethod
    def _ensure_variant_available(variant):
        if not variant.is_active:
            raise InactiveVariantError('Вариант товара неактивен.')
        if not variant.product.is_active:
            raise InactiveVariantError('Товар неактивен.')

    @staticmethod
    def _ensure_stock_available(variant, quantity):
        if not StockService.check_availability(variant, quantity):
            raise NotEnoughStockError('Недостаточно товара на складе.')

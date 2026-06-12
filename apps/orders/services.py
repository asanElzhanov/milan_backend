from dataclasses import dataclass
from decimal import Decimal
import uuid
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import ProductVariant
from apps.catalog.services import NotEnoughStockError as StockNotEnoughStockError
from apps.catalog.services import StockService

from .models import Cart, CartItem, DeliveryMethod, Order, OrderItem, OrderStatusHistory


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


class CheckoutError(ValidationError):
    pass


class EmptyCartError(CheckoutError):
    pass


class InactiveProductError(CheckoutError):
    pass


class InvalidCheckoutDataError(CheckoutError):
    pass


@dataclass(frozen=True)
class DeliveryCalculation:
    delivery_price: Decimal
    requires_manager_calculation: bool
    message: str = ''


class DeliveryService:
    @classmethod
    def calculate_delivery(cls, delivery_method, subtotal, city='', address=''):
        if isinstance(subtotal, float):
            raise InvalidCheckoutDataError('Сумма корзины должна быть Decimal.')
        subtotal = Decimal(subtotal)
        if subtotal < Decimal('0.00'):
            raise InvalidCheckoutDataError('Сумма корзины не может быть отрицательной.')
        if not delivery_method.is_active:
            raise InvalidCheckoutDataError('Некорректный способ доставки.')
        if delivery_method.base_price < Decimal('0.00'):
            raise InvalidCheckoutDataError('Стоимость доставки не может быть отрицательной.')
        if (
            delivery_method.free_from_amount is not None
            and delivery_method.free_from_amount < Decimal('0.00')
        ):
            raise InvalidCheckoutDataError('Порог бесплатной доставки не может быть отрицательным.')

        if delivery_method.price_type == DeliveryMethod.PriceType.MANAGER_CALCULATION:
            return DeliveryCalculation(
                delivery_price=Decimal('0.00'),
                requires_manager_calculation=True,
                message='Стоимость доставки уточняется менеджером.',
            )

        if delivery_method.price_type == DeliveryMethod.PriceType.FREE:
            return DeliveryCalculation(
                delivery_price=Decimal('0.00'),
                requires_manager_calculation=False,
                message='Доставка бесплатная.',
            )

        if (
            delivery_method.free_from_amount is not None
            and subtotal >= delivery_method.free_from_amount
        ):
            return DeliveryCalculation(
                delivery_price=Decimal('0.00'),
                requires_manager_calculation=False,
                message='Доставка бесплатная от суммы заказа.',
            )

        return DeliveryCalculation(
            delivery_price=delivery_method.base_price,
            requires_manager_calculation=False,
        )


class OrderStatusError(ValidationError):
    pass


class InvalidOrderStatusTransitionError(OrderStatusError):
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


class CheckoutService:
    required_fields = (
        'customer_name',
        'phone',
        'email',
        'delivery_method',
    )

    @classmethod
    def checkout(
        cls,
        *,
        cart,
        user=None,
        customer_name,
        phone,
        email,
        city='',
        delivery_address='',
        delivery_method,
        comment='',
    ):
        checkout_data = {
            'customer_name': customer_name,
            'phone': phone,
            'email': email,
            'city': city,
            'delivery_address': delivery_address,
            'delivery_method': delivery_method,
            'comment': comment,
        }
        cls._validate_checkout_data(checkout_data)

        with transaction.atomic():
            locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
            items = cls._get_locked_items(locked_cart)
            if not items:
                raise EmptyCartError('Корзина пуста.')

            variants_by_id = cls._get_locked_variants(items)
            order_items_data = []
            items_subtotal = Decimal('0.00')

            for item in items:
                variant = variants_by_id[item.variant_id]
                cls._ensure_variant_can_be_ordered(variant)
                cls._ensure_stock_available(variant, item.quantity)

                unit_price = cls.get_effective_price(variant)
                total_price = unit_price * item.quantity
                items_subtotal += total_price
                order_items_data.append({
                    'variant': variant,
                    'product_name': variant.product.name,
                    'product_slug': variant.product.slug,
                    'sku': variant.sku,
                    'size_name': variant.size.value if variant.size else '',
                    'color_name': variant.color.name if variant.color else '',
                    'unit_price': unit_price,
                    'quantity': item.quantity,
                    'total_price': total_price,
                })

            delivery_method = cls._get_delivery_method(checkout_data['delivery_method'])
            delivery = DeliveryService.calculate_delivery(
                delivery_method=delivery_method,
                subtotal=items_subtotal,
                city=checkout_data.get('city') or '',
                address=checkout_data.get('delivery_address') or '',
            )
            total_amount = items_subtotal + delivery.delivery_price

            order = Order.objects.create(
                user=user if user and user.is_authenticated else None,
                customer_name=checkout_data['customer_name'],
                phone=checkout_data['phone'],
                email=checkout_data['email'],
                city=checkout_data.get('city') or '',
                delivery_address=checkout_data.get('delivery_address') or '',
                delivery_method=delivery_method.code,
                delivery_method_ref=delivery_method,
                delivery_method_name=delivery_method.name,
                delivery_price=delivery.delivery_price,
                delivery_price_is_final=not delivery.requires_manager_calculation,
                total_amount=total_amount,
                status=Order.Status.NEW,
                payment_status=Order.PaymentStatus.UNPAID,
                comment=checkout_data.get('comment') or '',
            )

            for item_data in order_items_data:
                OrderItem.objects.create(order=order, **item_data)
                cls._write_off_stock(
                    variant=item_data['variant'],
                    quantity=item_data['quantity'],
                    user=user,
                    order=order,
                )

            locked_cart.items.select_for_update().delete()
            OrderStatusHistory.objects.create(
                order=order,
                old_status=None,
                new_status=Order.Status.NEW,
            )

            return order

    @staticmethod
    def get_effective_price(variant):
        return variant.variant_price if variant.variant_price is not None else variant.product.price

    @classmethod
    def _validate_checkout_data(cls, data):
        for field in cls.required_fields:
            if not data.get(field):
                raise InvalidCheckoutDataError(f'Поле {field} обязательно.')
        cls._get_delivery_method(data['delivery_method'])

    @staticmethod
    def _get_delivery_method(delivery_method):
        try:
            return DeliveryMethod.objects.get(code=delivery_method, is_active=True)
        except DeliveryMethod.DoesNotExist as exc:
            raise InvalidCheckoutDataError('Некорректный способ доставки.') from exc

    @staticmethod
    def _get_locked_items(cart):
        return list(
            CartItem.objects.select_for_update(of=('self',))
            .filter(cart=cart)
            .select_related('variant__product', 'variant__color', 'variant__size')
            .order_by('id')
        )

    @staticmethod
    def _get_locked_variants(items):
        variant_ids = sorted({item.variant_id for item in items})
        variants = (
            ProductVariant.objects.select_for_update(of=('self',))
            .select_related('product', 'color', 'size')
            .filter(pk__in=variant_ids)
            .order_by('id')
        )
        return {variant.id: variant for variant in variants}

    @staticmethod
    def _ensure_variant_can_be_ordered(variant):
        if not variant.is_active:
            raise InactiveVariantError('Вариант товара неактивен.')
        if not variant.product.is_active:
            raise InactiveProductError('Товар неактивен.')

    @staticmethod
    def _ensure_stock_available(variant, quantity):
        if variant.stock_quantity < quantity:
            raise NotEnoughStockError('Недостаточно товара на складе.')

    @staticmethod
    def _write_off_stock(*, variant, quantity, user, order):
        try:
            StockService.sale(
                variant=variant,
                quantity=quantity,
                user=user if user and user.is_authenticated else None,
                comment=f'Заказ #{order.order_number}',
            )
        except StockNotEnoughStockError as exc:
            raise NotEnoughStockError('Недостаточно товара на складе.') from exc


OrderCreateService = CheckoutService


class OrderStatusService:
    allowed_transitions = {
        Order.Status.NEW: {Order.Status.WAITING_PAYMENT, Order.Status.PAID, Order.Status.CANCELLED},
        Order.Status.WAITING_PAYMENT: {Order.Status.PAID, Order.Status.CANCELLED},
        Order.Status.PAID: {Order.Status.PROCESSING, Order.Status.CANCELLED},
        Order.Status.PROCESSING: {Order.Status.SHIPPED, Order.Status.CANCELLED},
        Order.Status.SHIPPED: {Order.Status.COMPLETED},
        Order.Status.COMPLETED: {Order.Status.RETURNED},
        Order.Status.CANCELLED: set(),
        Order.Status.RETURNED: set(),
    }
    cancellable_statuses = {
        Order.Status.NEW,
        Order.Status.WAITING_PAYMENT,
        Order.Status.PAID,
        Order.Status.PROCESSING,
    }

    @classmethod
    def change_status(cls, order, new_status, changed_by=None, comment=''):
        cls._validate_status(new_status)
        with transaction.atomic():
            locked_order = cls._lock_order(order)
            old_status = locked_order.status
            if old_status == new_status:
                return locked_order
            cls._ensure_transition_allowed(old_status, new_status)
            locked_order.status = new_status
            locked_order.save(update_fields=['status', 'updated_at'])
            cls._create_history(
                order=locked_order,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                comment=comment,
            )
            return locked_order

    @classmethod
    def cancel_order(cls, order, changed_by=None, comment=''):
        with transaction.atomic():
            locked_order = cls._lock_order(order)
            old_status = locked_order.status
            if old_status == Order.Status.CANCELLED:
                return locked_order
            if old_status not in cls.cancellable_statuses:
                raise InvalidOrderStatusTransitionError(
                    f'Нельзя отменить заказ из статуса {old_status}.'
                )

            cls._return_order_stock(locked_order, changed_by=changed_by)
            locked_order.status = Order.Status.CANCELLED
            locked_order.payment_status = Order.PaymentStatus.CANCELLED
            locked_order.save(update_fields=['status', 'payment_status', 'updated_at'])
            cls._create_history(
                order=locked_order,
                old_status=old_status,
                new_status=Order.Status.CANCELLED,
                changed_by=changed_by,
                comment=comment,
            )
            return locked_order

    @classmethod
    def mark_paid(cls, order, changed_by=None, comment=''):
        with transaction.atomic():
            locked_order = cls._lock_order(order)
            old_status = locked_order.status
            if old_status not in {Order.Status.NEW, Order.Status.WAITING_PAYMENT, Order.Status.PAID}:
                raise InvalidOrderStatusTransitionError(
                    f'Нельзя отметить оплаченным заказ из статуса {old_status}.'
                )

            locked_order.payment_status = Order.PaymentStatus.PAID
            update_fields = ['payment_status', 'updated_at']
            if old_status != Order.Status.PAID:
                locked_order.status = Order.Status.PAID
                update_fields.append('status')
            locked_order.save(update_fields=update_fields)

            if old_status != Order.Status.PAID:
                cls._create_history(
                    order=locked_order,
                    old_status=old_status,
                    new_status=Order.Status.PAID,
                    changed_by=changed_by,
                    comment=comment,
                )
            return locked_order

    @classmethod
    def _lock_order(cls, order):
        order_id = order.pk if isinstance(order, Order) else order
        return (
            Order.objects.select_for_update()
            .prefetch_related('items__variant')
            .get(pk=order_id)
        )

    @staticmethod
    def _validate_status(status):
        valid_statuses = {choice for choice, _ in Order.Status.choices}
        if status not in valid_statuses:
            raise InvalidOrderStatusTransitionError('Некорректный статус заказа.')

    @classmethod
    def _ensure_transition_allowed(cls, old_status, new_status):
        if new_status not in cls.allowed_transitions.get(old_status, set()):
            raise InvalidOrderStatusTransitionError(
                f'Недопустимый переход статуса {old_status} -> {new_status}.'
            )

    @staticmethod
    def _create_history(*, order, old_status, new_status, changed_by=None, comment=''):
        return OrderStatusHistory.objects.create(
            order=order,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by if changed_by and changed_by.is_authenticated else None,
            comment=comment,
        )

    @staticmethod
    def _return_order_stock(order, changed_by=None):
        for item in order.items.all():
            StockService.cancel_order(
                variant=item.variant,
                quantity=item.quantity,
                user=changed_by if changed_by and changed_by.is_authenticated else None,
                comment=f'Отмена заказа #{order.order_number}',
            )

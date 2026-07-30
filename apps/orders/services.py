from dataclasses import dataclass
from decimal import Decimal
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.catalog.services import NotEnoughStockError as StockNotEnoughStockError
from apps.catalog.services import StockService

from .models import (
    Cart,
    CartItem,
    DeliveryMethod,
    Order,
    OrderItem,
    OrderStatusHistory,
    PromoCode,
    PromoCodeUsage,
)


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


class PromoCodeError(CheckoutError):
    pass


class PromoCodeNotFoundError(PromoCodeError):
    pass


class PromoCodeInactiveError(PromoCodeError):
    pass


class PromoCodeExpiredError(PromoCodeError):
    pass


class PromoCodeNotStartedError(PromoCodeError):
    pass


class PromoCodeUsageLimitExceededError(PromoCodeError):
    pass


class PromoCodeMinAmountError(PromoCodeError):
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

        if delivery_method.price_type != DeliveryMethod.PriceType.FIXED:
            raise InvalidCheckoutDataError('Некорректный тип цены доставки.')

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
    def add_item(cls, cart, variant, quantity, anonymous_id_hash=''):
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
            old_quantity = 0 if item is None else item.quantity
            new_quantity = quantity if item is None else item.quantity + quantity
            cls._ensure_stock_available(variant, new_quantity)

            if item is None:
                item = CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
            else:
                item.quantity = new_quantity
                item.save(update_fields=['quantity', 'updated_at'])
            cls._record_cart_delta(
                cart=cart,
                item=item,
                delta=new_quantity - old_quantity,
                anonymous_id_hash=anonymous_id_hash,
            )
            return item, cart

    @classmethod
    def update_item(cls, cart, item_or_variant, quantity, anonymous_id_hash=''):
        quantity = cls._validate_quantity(quantity)
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item(cart, item_or_variant)
            variant = cls._lock_variant(item.variant_id)
            cls._ensure_variant_available(variant)
            cls._ensure_stock_available(variant, quantity)

            old_quantity = item.quantity
            if old_quantity != quantity:
                item.quantity = quantity
                item.save(update_fields=['quantity', 'updated_at'])
                cls._record_cart_delta(
                    cart=cart,
                    item=item,
                    delta=quantity - old_quantity,
                    anonymous_id_hash=anonymous_id_hash,
                )
            return item, cart

    @classmethod
    def update_item_by_id(cls, cart, item_id, quantity, anonymous_id_hash=''):
        quantity = cls._validate_quantity(quantity)
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item_by_id(cart, item_id)
            variant = cls._lock_variant(item.variant_id)
            cls._ensure_variant_available(variant)
            cls._ensure_stock_available(variant, quantity)

            old_quantity = item.quantity
            if old_quantity != quantity:
                item.quantity = quantity
                item.save(update_fields=['quantity', 'updated_at'])
                cls._record_cart_delta(
                    cart=cart,
                    item=item,
                    delta=quantity - old_quantity,
                    anonymous_id_hash=anonymous_id_hash,
                )
            return item, cart

    @classmethod
    def remove_item(cls, cart, item_or_variant, anonymous_id_hash=''):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item(cart, item_or_variant)
            cls._record_cart_delta(
                cart=cart,
                item=item,
                delta=-item.quantity,
                anonymous_id_hash=anonymous_id_hash,
                operation='delete',
            )
            item.delete()
            return cart

    @classmethod
    def remove_item_by_id(cls, cart, item_id, anonymous_id_hash=''):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            item = cls._lock_item_by_id(cart, item_id)
            cls._record_cart_delta(
                cart=cart,
                item=item,
                delta=-item.quantity,
                anonymous_id_hash=anonymous_id_hash,
                operation='delete',
            )
            item.delete()
            return cart

    @classmethod
    def clear_cart(cls, cart, anonymous_id_hash=''):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            items = list(
                cart.items.select_for_update().select_related('variant__product').order_by('id')
            )
            for item in items:
                cls._record_cart_delta(
                    cart=cart,
                    item=item,
                    delta=-item.quantity,
                    anonymous_id_hash=anonymous_id_hash,
                    operation='clear',
                )
            cart.items.all().delete()
            cart.promo_code = None
            cart.save(update_fields=['promo_code', 'updated_at'])
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
        promo_code = None
        discount_amount = Decimal('0.00')
        total = subtotal
        if cart.promo_code_id and subtotal > Decimal('0.00'):
            try:
                promo_code = cart.promo_code
                PromoCodeService.validate_promo(promo_code, subtotal, user=cart.user)
                discount_amount = PromoCodeService.calculate_discount(promo_code, subtotal)
                total = max(subtotal - discount_amount, Decimal('0.00'))
            except PromoCodeError:
                promo_code = None
                discount_amount = Decimal('0.00')
                total = subtotal
        return {
            'items_count': len(items),
            'total_quantity': total_quantity,
            'subtotal': subtotal,
            'promo_code': promo_code,
            'discount_amount': discount_amount,
            'total_after_discount': total,
            'total': total,
        }

    @classmethod
    def apply_promo_code(cls, cart, code, user=None):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            if not cart.items.exists():
                raise CartError('Корзина пуста.')
            result = PromoCodeService.apply_to_cart(cart, code, user=user)
            cart.promo_code = result['promo_code']
            cart.save(update_fields=['promo_code', 'updated_at'])
            return cart

    @classmethod
    def remove_promo_code(cls, cart):
        with transaction.atomic():
            cart = cls._lock_cart(cart)
            cart.promo_code = None
            cart.save(update_fields=['promo_code', 'updated_at'])
            return cart

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

    @staticmethod
    def _record_cart_delta(*, cart, item, delta, anonymous_id_hash='', operation='quantity'):
        if not delta:
            return
        if not cart.user_id and not anonymous_id_hash:
            return
        from apps.recommendations.constants import EventSource, EventType, RecommendationContext
        from apps.recommendations.services import RecommendationEventService

        event_type = EventType.CART_ADD if delta > 0 else EventType.CART_REMOVE
        timestamp = item.updated_at or item.created_at or timezone.now()
        RecommendationEventService.record_business_event(
            event_type=event_type,
            source=EventSource.CART,
            user=cart.user if cart.user_id else None,
            anonymous_id_hash=anonymous_id_hash,
            product=item.variant.product,
            variant=item.variant,
            context=RecommendationContext.CART,
            value=delta,
            deduplication_key=f'{event_type}:{item.id}:{operation}:{timestamp.isoformat()}',
        )


class PromoCodeService:
    money_quant = Decimal('0.01')

    @classmethod
    def normalize_code(cls, code):
        return str(code or '').strip().upper()

    @classmethod
    def get_active_promo(cls, code, *, for_update=False):
        normalized_code = cls.normalize_code(code)
        if not normalized_code:
            raise PromoCodeNotFoundError('Промокод не найден.')

        queryset = PromoCode.objects.all()
        if for_update:
            queryset = queryset.select_for_update()
        try:
            promo_code = queryset.get(code=normalized_code)
        except PromoCode.DoesNotExist as exc:
            raise PromoCodeNotFoundError('Промокод не найден.') from exc

        if not promo_code.is_active:
            raise PromoCodeInactiveError('Промокод неактивен.')
        return promo_code

    @classmethod
    def validate_promo(cls, promo_code, subtotal, user=None):
        subtotal = cls._normalize_money(subtotal)
        now = timezone.now()

        if not promo_code.is_active:
            raise PromoCodeInactiveError('Промокод неактивен.')
        if promo_code.valid_from and now < promo_code.valid_from:
            raise PromoCodeNotStartedError('Промокод еще не начал действовать.')
        if promo_code.valid_until and now > promo_code.valid_until:
            raise PromoCodeExpiredError('Срок действия промокода истек.')
        if promo_code.min_order_amount is not None and subtotal < promo_code.min_order_amount:
            raise PromoCodeMinAmountError('Минимальная сумма заказа для промокода не достигнута.')
        if promo_code.usage_limit is not None and promo_code.used_count >= promo_code.usage_limit:
            raise PromoCodeUsageLimitExceededError('Лимит использований промокода исчерпан.')
        return promo_code

    @classmethod
    def calculate_discount(cls, promo_code, subtotal):
        subtotal = cls._normalize_money(subtotal)
        if subtotal <= Decimal('0.00'):
            return Decimal('0.00')

        if promo_code.discount_type == PromoCode.DiscountType.PERCENT:
            discount = subtotal * promo_code.value / Decimal('100')
        elif promo_code.discount_type == PromoCode.DiscountType.FIXED:
            discount = promo_code.value
        else:
            raise PromoCodeError('Некорректный тип скидки.')

        discount = min(discount, subtotal)
        return discount.quantize(cls.money_quant)

    @classmethod
    def apply_to_cart(cls, cart, code, user=None):
        promo_code = cls.get_active_promo(code)
        totals = CartService.recalculate_cart(cart)
        subtotal = cls._normalize_money(totals['subtotal'])
        cls.validate_promo(promo_code, subtotal, user=user)
        discount_amount = cls.calculate_discount(promo_code, subtotal)
        return cls._build_result(promo_code, subtotal, discount_amount)

    @classmethod
    def apply_to_checkout(cls, cart, code, user=None, subtotal=None):
        promo_code = cls.get_active_promo(code, for_update=True)
        if subtotal is None:
            totals = CartService.recalculate_cart(cart)
            subtotal = totals['subtotal']
        subtotal = cls._normalize_money(subtotal)
        cls.validate_promo(promo_code, subtotal, user=user)
        discount_amount = cls.calculate_discount(promo_code, subtotal)
        return cls._build_result(promo_code, subtotal, discount_amount)

    @classmethod
    def mark_as_used(cls, promo_code, *, order, user=None):
        with transaction.atomic():
            updated = (
                PromoCode.objects
                .filter(pk=promo_code.pk)
                .filter(Q(usage_limit__isnull=True) | Q(used_count__lt=F('usage_limit')))
                .update(used_count=F('used_count') + 1)
            )
            if not updated:
                raise PromoCodeUsageLimitExceededError('Лимит использований промокода исчерпан.')
            promo_code.refresh_from_db(fields=['used_count'])
            return PromoCodeUsage.objects.create(
                promo_code=promo_code,
                order=order,
                user=user if user and user.is_authenticated else None,
            )

    @classmethod
    def _build_result(cls, promo_code, subtotal, discount_amount):
        total_after_discount = max(subtotal - discount_amount, Decimal('0.00'))
        return {
            'promo_code': promo_code,
            'discount_amount': discount_amount,
            'subtotal': subtotal,
            'total_after_discount': total_after_discount.quantize(cls.money_quant),
        }

    @classmethod
    def _normalize_money(cls, amount):
        if isinstance(amount, float):
            raise PromoCodeError('Сумма должна быть Decimal.')
        return Decimal(amount).quantize(cls.money_quant)


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
        promo_code=None,
        comment='',
        anonymous_id_hash='',
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
                    'product_name': variant.product.name_ru,
                    'product_slug': variant.product.slug,
                    'sku': variant.sku,
                    'size_name': variant.size.value if variant.size else '',
                    'color_name': variant.color.name_ru if variant.color else '',
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
            promo_code_data = None
            discount_amount = Decimal('0.00')
            effective_promo_code = promo_code or (
                locked_cart.promo_code.code if locked_cart.promo_code_id else None
            )
            if effective_promo_code:
                promo_code_data = PromoCodeService.apply_to_checkout(
                    cart=locked_cart,
                    code=effective_promo_code,
                    user=user,
                    subtotal=items_subtotal,
                )
                discount_amount = promo_code_data['discount_amount']
            total_amount = items_subtotal - discount_amount + delivery.delivery_price

            order = Order.objects.create(
                user=user if user and user.is_authenticated else None,
                customer_name=checkout_data['customer_name'],
                phone=checkout_data['phone'],
                email=checkout_data['email'],
                city=checkout_data.get('city') or '',
                delivery_address=checkout_data.get('delivery_address') or '',
                delivery_method=delivery_method.code,
                delivery_method_ref=delivery_method,
                delivery_method_code=delivery_method.code,
                delivery_method_name=delivery_method.name_ru,
                items_total=items_subtotal,
                delivery_price=delivery.delivery_price,
                delivery_requires_manager_calculation=delivery.requires_manager_calculation,
                delivery_price_is_final=not delivery.requires_manager_calculation,
                promo_code=promo_code_data['promo_code'] if promo_code_data is not None else None,
                promo_code_text=(
                    promo_code_data['promo_code'].code if promo_code_data is not None else ''
                ),
                discount_amount=discount_amount,
                total_amount=total_amount,
                status=Order.Status.NEW,
                payment_status=Order.PaymentStatus.UNPAID,
                comment=checkout_data.get('comment') or '',
            )

            created_order_items = []
            for item_data in order_items_data:
                order_item = OrderItem.objects.create(order=order, **item_data)
                created_order_items.append(order_item)
                cls._write_off_stock(
                    variant=item_data['variant'],
                    quantity=item_data['quantity'],
                    user=user,
                    order=order,
                )

            if order.user_id or anonymous_id_hash:
                from apps.recommendations.constants import EventSource, EventType, RecommendationContext
                from apps.recommendations.services import RecommendationEventService

                for order_item in created_order_items:
                    RecommendationEventService.record_business_event(
                        event_type=EventType.ORDER_CREATED,
                        source=EventSource.ORDER,
                        user=order.user,
                        anonymous_id_hash=anonymous_id_hash,
                        product=order_item.variant.product,
                        variant=order_item.variant,
                        order_item=order_item,
                        context=RecommendationContext.HOME,
                        value=order_item.quantity,
                        deduplication_key=f'order_created:{order_item.id}',
                    )

            if promo_code_data is not None:
                PromoCodeService.mark_as_used(
                    promo_code_data['promo_code'],
                    order=order,
                    user=user,
                )

            locked_cart.items.select_for_update().delete()
            locked_cart.promo_code = None
            locked_cart.save(update_fields=['promo_code', 'updated_at'])
            OrderStatusHistory.objects.create(
                order=order,
                old_status=None,
                new_status=Order.Status.NEW,
            )
            from apps.notifications.services import EmailNotificationService
            from apps.notifications.services import NotificationService

            EmailNotificationService.schedule_order_created_email(order)
            transaction.on_commit(lambda: NotificationService.notify_new_order(order))
            cls._schedule_auto_cancel(order)

            return order

    @staticmethod
    def _schedule_auto_cancel(order):
        """Запланировать авто-отмену заказа, если он не будет оплачен вовремя.

        Ставит отложенную Celery-задачу с задержкой
        ``ORDER_PAYMENT_TIMEOUT_MINUTES``. Задача создаётся только после
        успешного коммита транзакции, чтобы не отменять несуществующий заказ.
        """
        timeout_minutes = getattr(settings, 'ORDER_PAYMENT_TIMEOUT_MINUTES', 30)
        if timeout_minutes <= 0:
            return

        from .tasks import cancel_unpaid_order

        order_id = order.id
        countdown = timeout_minutes * 60
        transaction.on_commit(
            lambda: cancel_unpaid_order.apply_async(args=[order_id], countdown=countdown)
        )

    @staticmethod
    def get_effective_price(variant):
        return variant.variant_price if variant.variant_price is not None else variant.product.price

    @classmethod
    def _validate_checkout_data(cls, data):
        for field in cls.required_fields:
            if not data.get(field):
                raise InvalidCheckoutDataError(f'Поле {field} обязательно.')
        delivery_method = cls._get_delivery_method(data['delivery_method'])
        if (
            delivery_method.delivery_type != DeliveryMethod.DeliveryType.PICKUP
            and not (data.get('delivery_address') or '').strip()
        ):
            raise InvalidCheckoutDataError('Адрес доставки обязателен.')

    @staticmethod
    def _get_delivery_method(delivery_method):
        try:
            if isinstance(delivery_method, DeliveryMethod):
                method = delivery_method
            elif isinstance(delivery_method, int) or str(delivery_method).isdigit():
                method = DeliveryMethod.objects.get(pk=delivery_method)
            else:
                method = DeliveryMethod.objects.get(code=delivery_method)
        except (DeliveryMethod.DoesNotExist, TypeError, ValueError) as exc:
            raise InvalidCheckoutDataError('Некорректный способ доставки.') from exc
        if not method.is_active:
            raise InvalidCheckoutDataError('Некорректный способ доставки.')
        return method

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
            history = cls._create_history(
                order=locked_order,
                old_status=old_status,
                new_status=new_status,
                changed_by=changed_by,
                comment=comment,
            )
            if new_status == Order.Status.RETURNED:
                # Partial/item-level returns require a dedicated commerce model.
                cls._record_recommendation_order_events(
                    locked_order,
                    event_type='return',
                    transition_id=history.id,
                )
            from apps.notifications.services import EmailNotificationService

            EmailNotificationService.schedule_order_status_changed_email(
                locked_order,
                old_status=old_status,
                new_status=new_status,
            )
            return locked_order

    @classmethod
    def cancel_order(cls, order, changed_by=None, comment='', *, expired=False):
        """Отменить заказ: вернуть товары на склад, сохранить историю.

        ``expired=True`` помечает заказ и платёж статусом «Время оплаты истекло»
        (авто-отмена по таймауту), иначе — «Отменён» (ручная отмена).
        """
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
            locked_order.payment_status = (
                Order.PaymentStatus.EXPIRED if expired else Order.PaymentStatus.CANCELLED
            )
            locked_order.save(update_fields=['status', 'payment_status', 'updated_at'])
            cls._cancel_pending_payments(locked_order, expired=expired)
            history = cls._create_history(
                order=locked_order,
                old_status=old_status,
                new_status=Order.Status.CANCELLED,
                changed_by=changed_by,
                comment=comment,
            )
            cls._record_recommendation_order_events(
                locked_order,
                event_type='order_cancel',
                transition_id=history.id,
            )
            from apps.notifications.services import EmailNotificationService

            EmailNotificationService.schedule_order_cancelled_email(locked_order)
            return locked_order

    @classmethod
    def mark_paid(cls, order, changed_by=None, comment=''):
        with transaction.atomic():
            locked_order = cls._lock_order(order)
            old_status = locked_order.status
            old_payment_status = locked_order.payment_status
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
            if old_payment_status != Order.PaymentStatus.PAID:
                from apps.notifications.services import EmailNotificationService
                from apps.notifications.services import NotificationService

                EmailNotificationService.schedule_order_paid_email(locked_order)
                transaction.on_commit(lambda: NotificationService.notify_payment_success(locked_order))
                cls._record_recommendation_order_events(
                    locked_order,
                    event_type='purchase',
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

    @staticmethod
    def _cancel_pending_payments(order, *, expired=False):
        """Пометить незавершённые платежи заказа отменёнными/просроченными.

        Успешные (SUCCESS) и уже возвращённые платежи не трогаем — это зона
        логики возврата средств.
        """
        from apps.payments.models import Payment

        target_status = Payment.Status.EXPIRED if expired else Payment.Status.CANCELLED
        order.payments.filter(status=Payment.Status.PENDING).update(
            status=target_status,
            updated_at=timezone.now(),
        )

    @staticmethod
    def _record_recommendation_order_events(order, *, event_type, transition_id=None):
        from apps.recommendations.constants import EventSource, RecommendationContext
        from apps.recommendations.models import UserProductEvent
        from apps.recommendations.services import RecommendationEventService

        items = order.items.select_related('variant__product').all()
        for item in items:
            anonymous_hash = ''
            if not order.user_id:
                anonymous_hash = UserProductEvent.objects.filter(
                    order_item=item,
                    event_type='order_created',
                ).values_list('anonymous_id_hash', flat=True).first() or ''
            if not order.user_id and not anonymous_hash:
                continue
            if event_type == 'purchase':
                deduplication_key = f'purchase:{item.id}'
            else:
                deduplication_key = f'{event_type}:{transition_id}:{item.id}'
            RecommendationEventService.record_business_event(
                event_type=event_type,
                source=EventSource.ORDER,
                user=order.user,
                anonymous_id_hash=anonymous_hash,
                product=item.variant.product,
                variant=item.variant,
                order_item=item,
                context=RecommendationContext.HOME,
                value=item.quantity,
                deduplication_key=deduplication_key,
            )

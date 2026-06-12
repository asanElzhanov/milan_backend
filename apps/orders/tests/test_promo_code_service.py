from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import (
    Cart,
    CartItem,
    DeliveryMethod,
    Order,
    PromoCode,
    PromoCodeUsage,
)
from apps.orders.services import (
    CartService,
    CheckoutService,
    PromoCodeExpiredError,
    PromoCodeInactiveError,
    PromoCodeMinAmountError,
    PromoCodeNotStartedError,
    PromoCodeService,
    PromoCodeUsageLimitExceededError,
)


class PromoCodeServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Promo Shoes', slug='promo-shoes')
        self.brand = Brand.objects.create(name='Promo Brand', slug='promo-brand')
        self.product = Product.objects.create(
            sku='SKU-PROMO-SERVICE',
            name='Promo Product',
            slug='promo-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-PROMO-SERVICE',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.user = User.objects.create_user(email='promo-service@example.com')
        self.cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=2)
        self.courier_delivery = DeliveryMethod.objects.get(code='courier')
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])

    def create_promo_code(self, **overrides):
        data = {
            'code': 'PROMO10',
            'discount_type': PromoCode.DiscountType.PERCENT,
            'value': Decimal('10.00'),
        }
        data.update(overrides)
        return PromoCode.objects.create(**data)

    def checkout(self, promo_code):
        return CheckoutService.checkout(
            cart=self.cart,
            user=self.user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            promo_code=promo_code,
        )

    def test_normalize_code_strips_and_uppercases(self):
        self.assertEqual(PromoCodeService.normalize_code(' promo10 '), 'PROMO10')

    def test_active_promo_applies_to_cart(self):
        promo_code = self.create_promo_code()

        result = PromoCodeService.apply_to_cart(self.cart, ' promo10 ', user=self.user)

        self.assertEqual(result['promo_code'], promo_code)
        self.assertEqual(result['subtotal'], Decimal('240.00'))
        self.assertEqual(result['discount_amount'], Decimal('24.00'))
        self.assertEqual(result['total_after_discount'], Decimal('216.00'))

    def test_inactive_promo_does_not_apply(self):
        self.create_promo_code(is_active=False)

        with self.assertRaises(PromoCodeInactiveError):
            PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

    def test_expired_promo_does_not_apply(self):
        self.create_promo_code(valid_until=timezone.now() - timedelta(days=1))

        with self.assertRaises(PromoCodeExpiredError):
            PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

    def test_not_started_promo_does_not_apply(self):
        self.create_promo_code(valid_from=timezone.now() + timedelta(days=1))

        with self.assertRaises(PromoCodeNotStartedError):
            PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

    def test_usage_limit_blocks_promo(self):
        self.create_promo_code(usage_limit=1, used_count=1)

        with self.assertRaises(PromoCodeUsageLimitExceededError):
            PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

    def test_min_order_amount_is_checked(self):
        self.create_promo_code(min_order_amount=Decimal('300.00'))

        with self.assertRaises(PromoCodeMinAmountError):
            PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

    def test_percent_discount_is_calculated(self):
        promo_code = self.create_promo_code(value=Decimal('12.50'))

        discount = PromoCodeService.calculate_discount(promo_code, Decimal('240.00'))

        self.assertEqual(discount, Decimal('30.00'))

    def test_fixed_discount_is_calculated(self):
        promo_code = self.create_promo_code(
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('50.00'),
        )

        discount = PromoCodeService.calculate_discount(promo_code, Decimal('240.00'))

        self.assertEqual(discount, Decimal('50.00'))

    def test_discount_cannot_exceed_subtotal(self):
        promo_code = self.create_promo_code(
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('500.00'),
        )

        result = PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

        self.assertEqual(result['discount_amount'], Decimal('240.00'))
        self.assertEqual(result['total_after_discount'], Decimal('0.00'))

    def test_apply_to_cart_does_not_increment_used_count(self):
        promo_code = self.create_promo_code()

        PromoCodeService.apply_to_cart(self.cart, 'PROMO10', user=self.user)

        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 0)
        self.assertFalse(PromoCodeUsage.objects.exists())

    def test_checkout_increments_used_count_after_successful_order(self):
        promo_code = self.create_promo_code()

        order = self.checkout('PROMO10')

        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 1)
        self.assertEqual(order.promo_code, promo_code)
        self.assertEqual(order.promo_code_text, 'PROMO10')
        self.assertEqual(order.discount_amount, Decimal('24.00'))
        self.assertEqual(order.items_total, Decimal('240.00'))
        self.assertEqual(order.delivery_price, Decimal('1000.00'))
        self.assertEqual(order.total_amount, Decimal('1216.00'))
        usage = PromoCodeUsage.objects.get(order=order)
        self.assertEqual(usage.promo_code, promo_code)
        self.assertEqual(usage.user, self.user)

    def test_checkout_does_not_increment_used_count_when_checkout_rolls_back(self):
        promo_code = self.create_promo_code()

        with patch('apps.orders.services.StockService.sale', side_effect=ValidationError('boom')):
            with self.assertRaises(ValidationError):
                self.checkout('PROMO10')

        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 0)
        self.assertFalse(PromoCodeUsage.objects.exists())
        self.assertFalse(Order.objects.exists())

    def test_checkout_with_fixed_promo_code_saves_discount_snapshot(self):
        promo_code = self.create_promo_code(
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('50.00'),
        )

        order = self.checkout('PROMO10')

        self.assertEqual(order.promo_code, promo_code)
        self.assertEqual(order.promo_code_text, 'PROMO10')
        self.assertEqual(order.discount_amount, Decimal('50.00'))
        self.assertEqual(order.total_amount, Decimal('1190.00'))

    def test_checkout_uses_promo_code_stored_on_cart(self):
        promo_code = self.create_promo_code()
        CartService.apply_promo_code(self.cart, 'PROMO10', user=self.user)

        order = CheckoutService.checkout(
            cart=self.cart,
            user=self.user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
        )

        promo_code.refresh_from_db()
        self.cart.refresh_from_db()
        self.assertEqual(order.promo_code_text, 'PROMO10')
        self.assertEqual(order.discount_amount, Decimal('24.00'))
        self.assertEqual(order.total_amount, Decimal('1216.00'))
        self.assertEqual(promo_code.used_count, 1)
        self.assertIsNone(self.cart.promo_code)

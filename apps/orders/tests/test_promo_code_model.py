from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order, PromoCode, PromoCodeTier, PromoCodeUsage


class PromoCodeModelTests(TestCase):
    def test_tiered_promo_does_not_require_flat_value(self):
        promo = PromoCode(code='TIERS', discount_type=PromoCode.DiscountType.TIERED)
        promo.full_clean()
        promo.save()
        self.assertIsNone(promo.value)

    def test_flat_promo_requires_value(self):
        promo = PromoCode(code='NO-VALUE', discount_type=PromoCode.DiscountType.PERCENT)
        with self.assertRaises(ValidationError):
            promo.full_clean()

    def test_tier_rejects_invalid_quantity_percent_and_duplicate_threshold(self):
        promo = PromoCode.objects.create(code='TIERS', discount_type=PromoCode.DiscountType.TIERED)
        for quantity, percent in [(0, 10), (1, 0), (1, -1), (1, 101)]:
            with self.subTest(quantity=quantity, percent=percent):
                tier = PromoCodeTier(promo_code=promo, min_quantity=quantity, percent=percent)
                with self.assertRaises(ValidationError):
                    tier.full_clean()
        PromoCodeTier.objects.create(promo_code=promo, min_quantity=1, percent=10)
        with self.assertRaises(ValidationError):
            PromoCodeTier(promo_code=promo, min_quantity=1, percent=15).full_clean()

    def test_save_normalizes_code_to_uppercase(self):
        promo_code = PromoCode.objects.create(
            code=' summer10 ',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('10.00'),
        )

        self.assertEqual(promo_code.code, 'SUMMER10')
        self.assertEqual(str(promo_code), 'SUMMER10')

    def test_percent_discount_cannot_exceed_100(self):
        promo_code = PromoCode(
            code='TOO-MUCH',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('101.00'),
        )

        with self.assertRaises(ValidationError) as context:
            promo_code.full_clean()

        self.assertIn('value', context.exception.message_dict)

    def test_value_must_be_positive(self):
        promo_code = PromoCode(
            code='ZERO',
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('0.00'),
        )

        with self.assertRaises(ValidationError) as context:
            promo_code.full_clean()

        self.assertIn('value', context.exception.message_dict)

    def test_min_order_amount_cannot_be_negative(self):
        promo_code = PromoCode(
            code='NEGATIVE-MIN',
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('500.00'),
            min_order_amount=Decimal('-1.00'),
        )

        with self.assertRaises(ValidationError) as context:
            promo_code.full_clean()

        self.assertIn('min_order_amount', context.exception.message_dict)

    def test_used_count_cannot_exceed_usage_limit(self):
        promo_code = PromoCode(
            code='LIMIT',
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('500.00'),
            usage_limit=1,
            used_count=2,
        )

        with self.assertRaises(ValidationError) as context:
            promo_code.full_clean()

        self.assertIn('used_count', context.exception.message_dict)

    def test_valid_until_cannot_be_before_valid_from(self):
        now = timezone.now()
        promo_code = PromoCode(
            code='DATES',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('10.00'),
            valid_from=now,
            valid_until=now - timedelta(days=1),
        )

        with self.assertRaises(ValidationError) as context:
            promo_code.full_clean()

        self.assertIn('valid_until', context.exception.message_dict)

    def test_promo_code_usage_links_promo_code_order_and_user(self):
        user = User.objects.create_user(email='promo-usage@example.com')
        promo_code = PromoCode.objects.create(
            code='ORDER10',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('10.00'),
        )
        order = Order.objects.create(
            user=user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('1000.00'),
        )

        usage = PromoCodeUsage.objects.create(
            promo_code=promo_code,
            order=order,
            user=user,
        )

        self.assertEqual(usage.promo_code, promo_code)
        self.assertEqual(usage.order, order)
        self.assertEqual(usage.user, user)
        self.assertIn(order.order_number, str(usage))

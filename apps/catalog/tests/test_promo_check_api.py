from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.orders.models import PromoCode, PromoCodeTier


class PromoCheckApiTests(APITestCase):
    url = '/api/v1/catalog/promo/check/'

    def setUp(self):
        self.user = User.objects.create_user(email='promo-check@example.com')
        self.client.force_authenticate(user=self.user)

    def test_quantity_promo_check_returns_selected_percent(self):
        promo = PromoCode.objects.create(code='TIERS', discount_type=PromoCode.DiscountType.TIERED)
        for quantity, percent in [(1, 10), (2, 15), (3, 20)]:
            PromoCodeTier.objects.create(promo_code=promo, min_quantity=quantity, percent=percent)
        response = self.client.post(
            self.url, {'code': promo.code, 'order_amount': '200.00', 'total_quantity': 2}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['discount_value'], '15.00')
        self.assertEqual(response.data['discount_amount'], '30.00')
        self.assertEqual(response.data['final_amount'], '170.00')

    def test_quantity_promo_check_requires_positive_quantity(self):
        promo = PromoCode.objects.create(code='TIERS', discount_type=PromoCode.DiscountType.TIERED)
        PromoCodeTier.objects.create(promo_code=promo, min_quantity=1, percent=10)
        for quantity in [None, 0, -1, 1.5]:
            with self.subTest(quantity=quantity):
                payload = {'code': promo.code, 'order_amount': '200.00'}
                if quantity is not None:
                    payload['total_quantity'] = quantity
                response = self.client.post(self.url, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('total_quantity', response.data)


    def test_promo_check_uses_orders_promo_code_service(self):
        promo_code = PromoCode.objects.create(
            code='CHECK10',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('10.00'),
            usage_limit=1,
        )

        response = self.client.post(
            self.url,
            {'code': ' check10 ', 'order_amount': '200.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['code'], 'CHECK10')
        self.assertEqual(response.data['discount_type'], PromoCode.DiscountType.PERCENT)
        self.assertEqual(response.data['discount_value'], '10.00')
        self.assertEqual(response.data['discount_amount'], '20.00')
        self.assertEqual(response.data['final_amount'], '180.00')
        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 0)

    def test_promo_check_rejects_exhausted_orders_promo_code(self):
        PromoCode.objects.create(
            code='USEDUP',
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('25.00'),
            usage_limit=1,
            used_count=1,
        )

        response = self.client.post(
            self.url,
            {'code': 'USEDUP', 'order_amount': '200.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('code', response.data)

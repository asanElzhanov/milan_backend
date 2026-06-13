from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.orders.models import PromoCode


class PromoCheckApiTests(APITestCase):
    url = '/api/v1/catalog/promo/check/'

    def setUp(self):
        self.user = User.objects.create_user(email='promo-check@example.com')
        self.client.force_authenticate(user=self.user)

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

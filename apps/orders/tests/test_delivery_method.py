from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.models import DeliveryMethod


class DeliveryMethodModelTests(TestCase):
    def test_code_is_unique(self):
        DeliveryMethod.objects.create(
            name='Express',
            code='express',
            slug='express',
            delivery_type=DeliveryMethod.DeliveryType.COURIER,
        )

        with self.assertRaises(IntegrityError):
            DeliveryMethod.objects.create(
                name='Express Copy',
                code='express',
                slug='express-copy',
                delivery_type=DeliveryMethod.DeliveryType.COURIER,
            )

    def test_slug_is_unique(self):
        DeliveryMethod.objects.create(
            name='Express',
            code='express',
            slug='express',
            delivery_type=DeliveryMethod.DeliveryType.COURIER,
        )

        with self.assertRaises(IntegrityError):
            DeliveryMethod.objects.create(
                name='Express Copy',
                code='express-copy',
                slug='express',
                delivery_type=DeliveryMethod.DeliveryType.COURIER,
            )

    def test_negative_prices_are_invalid(self):
        method = DeliveryMethod(
            name='Invalid',
            code='invalid',
            slug='invalid',
            delivery_type=DeliveryMethod.DeliveryType.COURIER,
            base_price=Decimal('-1.00'),
            free_from_amount=Decimal('-1.00'),
        )

        with self.assertRaises(ValidationError):
            method.full_clean()

    def test_calculate_price_for_fixed_with_free_threshold(self):
        method = DeliveryMethod(
            name='Fixed',
            code='fixed',
            slug='fixed',
            delivery_type=DeliveryMethod.DeliveryType.COURIER,
            price_type=DeliveryMethod.PriceType.FIXED,
            base_price=Decimal('1000.00'),
            free_from_amount=Decimal('10000.00'),
        )

        self.assertEqual(method.calculate_price(Decimal('9999.00')), (Decimal('1000.00'), True))
        self.assertEqual(method.calculate_price(Decimal('10000.00')), (Decimal('0.00'), True))

    def test_manager_calculation_is_not_final(self):
        method = DeliveryMethod(
            name='Manager',
            code='manager',
            slug='manager',
            delivery_type=DeliveryMethod.DeliveryType.KAZAKHSTAN_DELIVERY,
            price_type=DeliveryMethod.PriceType.MANAGER_CALCULATION,
        )

        self.assertEqual(method.calculate_price(Decimal('1000.00')), (Decimal('0.00'), False))


class DeliveryMethodAPITests(APITestCase):
    list_url = '/api/v1/orders/delivery-methods/'

    def setUp(self):
        DeliveryMethod.objects.all().delete()
        self.pickup = DeliveryMethod.objects.create(
            name='Самовывоз',
            code='pickup',
            slug='pickup',
            delivery_type=DeliveryMethod.DeliveryType.PICKUP,
            price_type=DeliveryMethod.PriceType.FREE,
            sort_order=20,
        )
        self.courier = DeliveryMethod.objects.create(
            name='Курьерская доставка',
            code='courier',
            slug='courier',
            delivery_type=DeliveryMethod.DeliveryType.COURIER,
            sort_order=10,
        )
        self.inactive = DeliveryMethod.objects.create(
            name='Archive',
            code='archive',
            slug='archive',
            delivery_type=DeliveryMethod.DeliveryType.COURIER,
            is_active=False,
            sort_order=30,
        )

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_delivery_method_list_returns_methods_ordered_by_sort_order(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [item['code'] for item in self.response_items(response)]
        self.assertEqual(codes, ['courier', 'pickup', 'archive'])

    def test_delivery_method_list_filters_active_methods(self):
        response = self.client.get(self.list_url, {'active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {item['code'] for item in self.response_items(response)}
        self.assertEqual(codes, {'courier', 'pickup'})

    def test_delivery_method_list_filters_inactive_methods(self):
        response = self.client.get(self.list_url, {'active': 'false'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {item['code'] for item in self.response_items(response)}
        self.assertEqual(codes, {'archive'})

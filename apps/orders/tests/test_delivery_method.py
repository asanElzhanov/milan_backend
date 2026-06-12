from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.orders.admin import DeliveryMethodAdmin
from apps.orders.models import DeliveryMethod
from apps.orders.services import DeliveryService, InvalidCheckoutDataError


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


class DeliveryMethodAdminTests(TestCase):
    def test_delivery_method_admin_is_registered(self):
        self.assertIsInstance(admin.site._registry[DeliveryMethod], DeliveryMethodAdmin)


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

    def test_delivery_method_list_returns_only_active_methods_ordered_by_sort_order(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [item['code'] for item in self.response_items(response)]
        self.assertEqual(codes, ['courier', 'pickup'])

    def test_delivery_method_list_does_not_expose_inactive_methods(self):
        response = self.client.get(self.list_url, {'active': 'false'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {item['code'] for item in self.response_items(response)}
        self.assertEqual(codes, {'courier', 'pickup'})
        self.assertNotIn('archive', codes)


class DeliveryServiceTests(TestCase):
    def make_method(self, **overrides):
        data = {
            'name': 'Delivery',
            'code': 'delivery',
            'slug': 'delivery',
            'delivery_type': DeliveryMethod.DeliveryType.COURIER,
            'price_type': DeliveryMethod.PriceType.FIXED,
            'base_price': Decimal('1000.00'),
            'is_active': True,
        }
        data.update(overrides)
        return DeliveryMethod(**data)

    def test_fixed_returns_base_price_as_decimal(self):
        method = self.make_method(base_price=Decimal('1500.00'))

        calculation = DeliveryService.calculate_delivery(method, Decimal('5000.00'))

        self.assertEqual(calculation.delivery_price, Decimal('1500.00'))
        self.assertIsInstance(calculation.delivery_price, Decimal)
        self.assertFalse(calculation.requires_manager_calculation)

    def test_free_returns_zero(self):
        method = self.make_method(
            price_type=DeliveryMethod.PriceType.FREE,
            base_price=Decimal('1500.00'),
        )

        calculation = DeliveryService.calculate_delivery(method, Decimal('5000.00'))

        self.assertEqual(calculation.delivery_price, Decimal('0.00'))
        self.assertFalse(calculation.requires_manager_calculation)

    def test_manager_calculation_returns_zero_and_requires_manager_flag(self):
        method = self.make_method(price_type=DeliveryMethod.PriceType.MANAGER_CALCULATION)

        calculation = DeliveryService.calculate_delivery(method, Decimal('5000.00'))

        self.assertEqual(calculation.delivery_price, Decimal('0.00'))
        self.assertTrue(calculation.requires_manager_calculation)
        self.assertIn('менеджером', calculation.message)

    def test_free_from_amount_makes_fixed_delivery_free_at_threshold(self):
        method = self.make_method(
            base_price=Decimal('1000.00'),
            free_from_amount=Decimal('10000.00'),
        )

        paid = DeliveryService.calculate_delivery(method, Decimal('9999.00'))
        free = DeliveryService.calculate_delivery(method, Decimal('10000.00'))

        self.assertEqual(paid.delivery_price, Decimal('1000.00'))
        self.assertEqual(free.delivery_price, Decimal('0.00'))
        self.assertFalse(free.requires_manager_calculation)

    def test_inactive_delivery_method_is_rejected(self):
        method = self.make_method(is_active=False)

        with self.assertRaises(InvalidCheckoutDataError):
            DeliveryService.calculate_delivery(method, Decimal('5000.00'))

    def test_float_subtotal_is_rejected(self):
        method = self.make_method()

        with self.assertRaises(InvalidCheckoutDataError):
            DeliveryService.calculate_delivery(method, 5000.00)

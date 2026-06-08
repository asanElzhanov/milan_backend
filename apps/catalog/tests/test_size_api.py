from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Size


class SizeModelTests(TestCase):
    def test_size_string_contains_type_and_value(self):
        size = Size(value='M', size_type=Size.SizeType.CLOTHES)

        self.assertEqual(str(size), 'clothes: M')

    def test_size_value_and_type_are_unique_together(self):
        Size.objects.create(value='M', size_type=Size.SizeType.CLOTHES)

        with self.assertRaises(IntegrityError):
            Size.objects.create(value='M', size_type=Size.SizeType.CLOTHES)

    def test_same_size_value_can_exist_for_different_types(self):
        clothes = Size.objects.create(value='M', size_type=Size.SizeType.CLOTHES)
        accessories = Size.objects.create(value='M', size_type=Size.SizeType.ACCESSORIES)

        self.assertNotEqual(clothes.id, accessories.id)


class SizeAPITests(APITestCase):
    list_url = '/api/v1/catalog/sizes/'

    def setUp(self):
        self.shoes_42 = Size.objects.create(
            value='42',
            size_type=Size.SizeType.SHOES,
            sort_order=42,
        )
        self.clothes_m = Size.objects.create(
            value='M',
            size_type=Size.SizeType.CLOTHES,
            sort_order=2,
        )
        self.accessory_one_size = Size.objects.create(
            value='One Size',
            size_type=Size.SizeType.ACCESSORIES,
            sort_order=1,
            is_active=False,
        )

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_size_list_returns_sizes_ordered_by_type_sort_order_and_value(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = [(item['size_type'], item['value']) for item in self.response_items(response)]
        self.assertEqual(values, [
            ('accessories', 'One Size'),
            ('clothes', 'M'),
            ('shoes', '42'),
        ])

    def test_size_list_filters_active_sizes(self):
        response = self.client.get(self.list_url, {'active': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = {item['value'] for item in self.response_items(response)}
        self.assertEqual(values, {'42', 'M'})

    def test_size_list_filters_inactive_sizes(self):
        response = self.client.get(self.list_url, {'active': 'false'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = {item['value'] for item in self.response_items(response)}
        self.assertEqual(values, {'One Size'})

    def test_size_list_filters_by_size_type(self):
        response = self.client.get(self.list_url, {'size_type': Size.SizeType.CLOTHES})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['value'], 'M')
        self.assertEqual(items[0]['size_type'], 'clothes')

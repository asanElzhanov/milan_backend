from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, Product


class ProductFilterTests(APITestCase):
    list_url = '/api/v1/catalog/products/'

    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='nike')
        self.discounted = Product.objects.create(
            sku='SKU-DISCOUNT',
            name_ru='Discounted',
            slug='discounted',
            category=category,
            brand=brand,
            price=Decimal('80.00'),
            old_price=Decimal('100.00'),
        )
        self.regular = Product.objects.create(
            sku='SKU-REGULAR',
            name_ru='Regular',
            slug='regular',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_product_list_filters_products_with_discount(self):
        response = self.client.get(self.list_url, {'has_discount': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slugs = {item['slug'] for item in self.response_items(response)}
        self.assertEqual(slugs, {'discounted'})

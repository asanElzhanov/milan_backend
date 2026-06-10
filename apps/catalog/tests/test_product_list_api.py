from decimal import Decimal
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, Color, Product, ProductImage, ProductVariant, Size


class ProductListApiTests(APITestCase):
    list_url = '/api/v1/catalog/products/'

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.category = Category.objects.create(name='Shoes', slug='shoes')
        self.other_category = Category.objects.create(name='Bags', slug='bags')
        self.brand = Brand.objects.create(name='Nike', slug='nike')
        self.other_brand = Brand.objects.create(name='Adidas', slug='adidas')
        self.color = Color.objects.create(name='Black', slug='black', hex_code='#000000')
        self.size_41 = Size.objects.create(value='41', size_type=Size.SizeType.SHOES, sort_order=1)
        self.size_42 = Size.objects.create(value='42', size_type=Size.SizeType.SHOES, sort_order=2)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def make_product(self, sku, name, **kwargs):
        data = {
            'sku': sku,
            'name': name,
            'category': self.category,
            'brand': self.brand,
            'price': Decimal('100.00'),
        }
        data.update(kwargs)
        return Product.objects.create(**data)

    def make_image_file(self, name='product.jpg'):
        return SimpleUploadedFile(name, b'image content', content_type='image/jpeg')

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def test_product_list_returns_only_active_products(self):
        active = self.make_product('SKU-ACTIVE', 'Active')
        self.make_product('SKU-INACTIVE', 'Inactive', is_active=False)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [active.slug])

    def test_product_list_is_paginated(self):
        for index in range(25):
            self.make_product(f'SKU-{index}', f'Product {index}')

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 25)
        self.assertEqual(len(response.data['results']), 24)

    def test_product_list_returns_main_image(self):
        product = self.make_product('SKU-IMAGE-LIST', 'Image Product')
        ProductImage.objects.create(
            product=product,
            image=self.make_image_file('first.jpg'),
            sort_order=1,
        )
        ProductImage.objects.create(
            product=product,
            image=self.make_image_file('main.jpg'),
            is_main=True,
            sort_order=2,
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = self.response_items(response)[0]
        self.assertIsNotNone(item['main_image'])
        self.assertIn('main', item['main_image'])

    def test_product_list_uses_first_image_when_main_image_is_missing(self):
        product = self.make_product('SKU-FIRST-IMAGE', 'First Image Product')
        ProductImage.objects.create(
            product=product,
            image=self.make_image_file('second.jpg'),
            sort_order=2,
        )
        ProductImage.objects.create(
            product=product,
            image=self.make_image_file('first.jpg'),
            sort_order=1,
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = self.response_items(response)[0]
        self.assertIn('first', item['main_image'])

    def test_product_list_returns_min_price_from_active_variants(self):
        product = self.make_product('SKU-MIN-PRICE', 'Min Price Product', price=Decimal('100.00'))
        ProductVariant.objects.create(
            product=product,
            color=self.color,
            size=self.size_41,
            sku='VAR-BASE',
            stock_quantity=2,
        )
        ProductVariant.objects.create(
            product=product,
            color=self.color,
            size=self.size_42,
            sku='VAR-CHEAP',
            stock_quantity=1,
            variant_price=Decimal('80.00'),
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = self.response_items(response)[0]
        self.assertEqual(Decimal(item['min_price']), Decimal('80.00'))

    def test_product_list_marks_in_stock_from_active_variant_stock(self):
        in_stock_product = self.make_product('SKU-IN-STOCK', 'In Stock Product')
        ProductVariant.objects.create(
            product=in_stock_product,
            color=self.color,
            size=self.size_41,
            sku='VAR-IN-STOCK',
            stock_quantity=1,
        )
        self.make_product('SKU-NO-VARIANTS', 'No Variants Product')

        response = self.client.get(self.list_url, {'ordering': 'name'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stock_by_slug = {item['slug']: item['in_stock'] for item in self.response_items(response)}
        self.assertTrue(stock_by_slug[in_stock_product.slug])
        self.assertFalse(stock_by_slug['no-variants-product'])

    def test_product_list_filters_by_category_and_brand(self):
        matching = self.make_product('SKU-MATCH', 'Matching Product')
        self.make_product(
            'SKU-OTHER-CATEGORY',
            'Other Category Product',
            category=self.other_category,
            brand=self.brand,
        )
        self.make_product(
            'SKU-OTHER-BRAND',
            'Other Brand Product',
            category=self.category,
            brand=self.other_brand,
        )

        response = self.client.get(
            self.list_url,
            {'category': str(self.category.id), 'brand_slug': self.brand.slug},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

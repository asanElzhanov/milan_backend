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
        self.other_color = Color.objects.create(name='White', slug='white', hex_code='#FFFFFF')
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

    def test_product_list_filters_by_parent_category_descendants(self):
        sneakers = Category.objects.create(name='Sneakers', slug='sneakers', parent=self.category)
        matching = self.make_product('SKU-CATEGORY-TREE', 'Category Tree Product', category=sneakers)
        self.make_product('SKU-CATEGORY-OTHER', 'Other Category Product', category=self.other_category)

        response = self.client.get(self.list_url, {'category_slug': self.category.slug})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_subcategory(self):
        sneakers = Category.objects.create(name='Sneakers', slug='sneakers', parent=self.category)
        boots = Category.objects.create(name='Boots', slug='boots', parent=self.category)
        matching = self.make_product('SKU-SUBCATEGORY', 'Subcategory Product', category=sneakers)
        self.make_product('SKU-BOOTS', 'Boots Product', category=boots)

        response = self.client.get(self.list_url, {'subcategory': sneakers.slug})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_active_variant_size(self):
        matching = self.make_product('SKU-SIZE-MATCH', 'Size Match Product')
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-SIZE-MATCH',
            stock_quantity=1,
        )
        inactive_match = self.make_product('SKU-SIZE-INACTIVE', 'Inactive Size Product')
        ProductVariant.objects.create(
            product=inactive_match,
            color=self.other_color,
            size=self.size_41,
            sku='VAR-SIZE-INACTIVE',
            stock_quantity=1,
            is_active=False,
        )
        other_size = self.make_product('SKU-SIZE-OTHER', 'Other Size Product')
        ProductVariant.objects.create(
            product=other_size,
            color=self.color,
            size=self.size_42,
            sku='VAR-SIZE-OTHER',
            stock_quantity=1,
        )

        response = self.client.get(self.list_url, {'size': self.size_41.value})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_active_variant_color(self):
        matching = self.make_product('SKU-COLOR-MATCH', 'Color Match Product')
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-COLOR-MATCH',
            stock_quantity=1,
        )
        inactive_match = self.make_product('SKU-COLOR-INACTIVE', 'Inactive Color Product')
        ProductVariant.objects.create(
            product=inactive_match,
            color=self.color,
            size=self.size_42,
            sku='VAR-COLOR-INACTIVE',
            stock_quantity=1,
            is_active=False,
        )
        other_color = self.make_product('SKU-COLOR-OTHER', 'Other Color Product')
        ProductVariant.objects.create(
            product=other_color,
            color=self.other_color,
            size=self.size_41,
            sku='VAR-COLOR-OTHER',
            stock_quantity=1,
        )

        response = self.client.get(self.list_url, {'color': self.color.slug})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_price_from_and_price_to_using_active_variant_price(self):
        matching = self.make_product('SKU-PRICE-MATCH', 'Price Match Product', price=Decimal('120.00'))
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-PRICE-MATCH',
            stock_quantity=1,
            variant_price=Decimal('80.00'),
        )
        inactive_variant_price = self.make_product(
            'SKU-PRICE-INACTIVE',
            'Inactive Variant Price Product',
            price=Decimal('150.00'),
        )
        ProductVariant.objects.create(
            product=inactive_variant_price,
            color=self.color,
            size=self.size_41,
            sku='VAR-PRICE-INACTIVE',
            stock_quantity=1,
            variant_price=Decimal('80.00'),
            is_active=False,
        )
        self.make_product('SKU-PRICE-OTHER', 'Other Price Product', price=Decimal('150.00'))

        response = self.client.get(
            self.list_url,
            {'price_from': '70.00', 'price_to': '90.00'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_in_stock(self):
        matching = self.make_product('SKU-STOCK-MATCH', 'Stock Match Product')
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-STOCK-MATCH',
            stock_quantity=1,
        )
        out_of_stock = self.make_product('SKU-STOCK-EMPTY', 'Stock Empty Product')
        ProductVariant.objects.create(
            product=out_of_stock,
            color=self.color,
            size=self.size_42,
            sku='VAR-STOCK-EMPTY',
            stock_quantity=0,
        )
        inactive_stock = self.make_product('SKU-STOCK-INACTIVE', 'Inactive Stock Product')
        ProductVariant.objects.create(
            product=inactive_stock,
            color=self.other_color,
            size=self.size_41,
            sku='VAR-STOCK-INACTIVE',
            stock_quantity=1,
            is_active=False,
        )

        response = self.client.get(self.list_url, {'in_stock': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_brand(self):
        matching = self.make_product('SKU-BRAND-MATCH', 'Brand Match Product', brand=self.other_brand)
        self.make_product('SKU-BRAND-OTHER', 'Brand Other Product', brand=self.brand)

        response = self.client.get(self.list_url, {'brand': self.other_brand.slug})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_is_new(self):
        matching = self.make_product('SKU-NEW-MATCH', 'New Match Product', is_new=True)
        self.make_product('SKU-NEW-OTHER', 'New Other Product', is_new=False)

        response = self.client.get(self.list_url, {'is_new': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_filters_by_is_sale(self):
        matching = self.make_product(
            'SKU-SALE-MATCH',
            'Sale Match Product',
            price=Decimal('80.00'),
            old_price=Decimal('100.00'),
        )
        self.make_product('SKU-SALE-OTHER', 'Sale Other Product', price=Decimal('100.00'))

        response = self.client.get(self.list_url, {'is_sale': 'true'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_orders_by_real_price(self):
        lower_variant_price = self.make_product(
            'SKU-ORDER-LOWER-VARIANT',
            'B Lower Variant Price',
            price=Decimal('120.00'),
        )
        ProductVariant.objects.create(
            product=lower_variant_price,
            color=self.color,
            size=self.size_41,
            sku='VAR-ORDER-LOWER-VARIANT',
            stock_quantity=1,
            variant_price=Decimal('80.00'),
        )
        product_price = self.make_product(
            'SKU-ORDER-PRODUCT',
            'A Product Price',
            price=Decimal('90.00'),
        )

        response = self.client.get(self.list_url, {'ordering': 'price'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item['slug'] for item in self.response_items(response)],
            [lower_variant_price.slug, product_price.slug],
        )

    def test_product_list_supports_sort_alias_for_ordering(self):
        second = self.make_product('SKU-SORT-B', 'B Sort Product')
        first = self.make_product('SKU-SORT-A', 'A Sort Product')

        response = self.client.get(self.list_url, {'sort': 'name'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item['slug'] for item in self.response_items(response)],
            [first.slug, second.slug],
        )

    def test_product_list_searches_by_product_name(self):
        matching = self.make_product('SKU-SEARCH-NAME', 'Air Zoom Pegasus')
        self.make_product('SKU-SEARCH-NAME-OTHER', 'Classic Tote')

        response = self.client.get(self.list_url, {'search': 'zoom'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_searches_by_brand_name(self):
        matching = self.make_product('SKU-SEARCH-BRAND', 'Running Shoe', brand=self.other_brand)
        self.make_product('SKU-SEARCH-BRAND-OTHER', 'Training Shoe', brand=self.brand)

        response = self.client.get(self.list_url, {'search': 'adid'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_searches_by_variant_sku(self):
        matching = self.make_product('SKU-SEARCH-VARIANT', 'Variant Search Product')
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-SEARCH-ALPHA',
            stock_quantity=1,
        )
        other = self.make_product('SKU-SEARCH-VARIANT-OTHER', 'Other Variant Search Product')
        ProductVariant.objects.create(
            product=other,
            color=self.other_color,
            size=self.size_42,
            sku='VAR-OTHER-BETA',
            stock_quantity=1,
        )

        response = self.client.get(self.list_url, {'search': 'alpha'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_search_returns_only_active_products(self):
        matching = self.make_product('SKU-SEARCH-ACTIVE', 'Visible Search Product')
        self.make_product('SKU-SEARCH-INACTIVE', 'Visible Search Product', is_active=False)

        response = self.client.get(self.list_url, {'search': 'visible'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_search_combines_with_catalog_filters(self):
        sneakers = Category.objects.create(name='Search Sneakers', slug='search-sneakers', parent=self.category)
        matching = self.make_product(
            'SKU-SEARCH-FILTER-MATCH',
            'Trail Runner',
            category=sneakers,
            price=Decimal('120.00'),
        )
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-TRAIL-MATCH',
            stock_quantity=2,
            variant_price=Decimal('80.00'),
        )
        wrong_color = self.make_product(
            'SKU-SEARCH-FILTER-COLOR',
            'Trail Runner Color',
            category=sneakers,
            price=Decimal('120.00'),
        )
        ProductVariant.objects.create(
            product=wrong_color,
            color=self.other_color,
            size=self.size_41,
            sku='VAR-TRAIL-COLOR',
            stock_quantity=2,
            variant_price=Decimal('80.00'),
        )
        wrong_price = self.make_product(
            'SKU-SEARCH-FILTER-PRICE',
            'Trail Runner Price',
            category=sneakers,
            price=Decimal('140.00'),
        )
        ProductVariant.objects.create(
            product=wrong_price,
            color=self.color,
            size=self.size_41,
            sku='VAR-TRAIL-PRICE',
            stock_quantity=2,
            variant_price=Decimal('140.00'),
        )
        wrong_stock = self.make_product(
            'SKU-SEARCH-FILTER-STOCK',
            'Trail Runner Stock',
            category=sneakers,
            price=Decimal('120.00'),
        )
        ProductVariant.objects.create(
            product=wrong_stock,
            color=self.color,
            size=self.size_41,
            sku='VAR-TRAIL-STOCK',
            stock_quantity=0,
            variant_price=Decimal('80.00'),
        )
        self.make_product(
            'SKU-SEARCH-FILTER-CATEGORY',
            'Trail Runner Category',
            category=self.other_category,
            price=Decimal('80.00'),
        )

        response = self.client.get(
            self.list_url,
            {
                'search': 'trail',
                'category': self.category.slug,
                'size': self.size_41.value,
                'color': self.color.slug,
                'price_from': '70.00',
                'price_to': '90.00',
                'in_stock': 'true',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

    def test_product_list_search_does_not_duplicate_products_matching_multiple_variant_skus(self):
        matching = self.make_product('SKU-SEARCH-DUPES', 'Duplicate Variant Search Product')
        ProductVariant.objects.create(
            product=matching,
            color=self.color,
            size=self.size_41,
            sku='VAR-DUPE-ONE',
            stock_quantity=1,
        )
        ProductVariant.objects.create(
            product=matching,
            color=self.other_color,
            size=self.size_42,
            sku='VAR-DUPE-TWO',
            stock_quantity=1,
        )

        response = self.client.get(self.list_url, {'search': 'dupe'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['slug'] for item in self.response_items(response)], [matching.slug])

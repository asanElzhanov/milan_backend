from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Color, Product, ProductVariant, Size, StockMovement


class StockApiTests(APITestCase):
    stock_url = '/api/v1/catalog/stock/'
    stock_adjust_url = '/api/v1/catalog/stock/adjust/'
    movements_url = '/api/v1/catalog/stock/movements/'

    def setUp(self):
        self.manager = User.objects.create_user(
            email='manager-stock@example.com',
            password='secret123',
            role=User.Role.MANAGER,
        )
        self.customer = User.objects.create_user(
            email='customer-stock@example.com',
            password='secret123',
        )
        self.category = Category.objects.create(name='Shoes', slug='shoes')
        self.other_category = Category.objects.create(name='Bags', slug='bags')
        self.brand = Brand.objects.create(name='Nike', slug='nike')
        self.other_brand = Brand.objects.create(name='Adidas', slug='adidas')
        self.black = Color.objects.create(name='Black', slug='black', hex_code='#000000')
        self.white = Color.objects.create(name='White', slug='white', hex_code='#FFFFFF')
        self.size_41 = Size.objects.create(value='41', size_type=Size.SizeType.SHOES, sort_order=1)
        self.size_42 = Size.objects.create(value='42', size_type=Size.SizeType.SHOES, sort_order=2)
        self.product = Product.objects.create(
            sku='SKU-STOCK-API',
            name='Stock API Product',
            slug='stock-api-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.other_product = Product.objects.create(
            sku='SKU-STOCK-API-OTHER',
            name='Other Stock API Product',
            slug='other-stock-api-product',
            category=self.other_category,
            brand=self.other_brand,
            price=Decimal('120.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.black,
            size=self.size_41,
            sku='VAR-STOCK-API',
            stock_quantity=5,
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.other_product,
            color=self.white,
            size=self.size_42,
            sku='VAR-STOCK-API-OTHER',
            stock_quantity=0,
        )
        StockMovement.objects.create(
            variant=self.variant,
            quantity=2,
            operation_type=StockMovement.OperationType.INCOME,
            user=self.manager,
            comment='Receipt',
        )
        StockMovement.objects.create(
            variant=self.variant,
            quantity=1,
            operation_type=StockMovement.OperationType.SALE,
            user=self.manager,
            comment='Sale',
        )

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def authenticate_manager(self):
        self.client.force_authenticate(self.manager)

    def test_manager_can_view_stock(self):
        self.authenticate_manager()

        response = self.client.get(self.stock_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual(len(items), 2)
        first = next(item for item in items if item['sku'] == self.variant.sku)
        self.assertEqual(first['variant_id'], self.variant.id)
        self.assertEqual(first['product_slug'], self.product.slug)
        self.assertEqual(first['category']['slug'], self.category.slug)
        self.assertEqual(first['brand']['slug'], self.brand.slug)
        self.assertEqual(first['size']['value'], self.size_41.value)
        self.assertEqual(first['color']['slug'], self.black.slug)
        self.assertEqual(first['stock_quantity'], 5)
        self.assertTrue(first['is_active'])
        self.assertTrue(first['in_stock'])

    def test_customer_cannot_view_stock(self):
        self.client.force_authenticate(self.customer)

        response = self.client.get(self.stock_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_view_stock(self):
        response = self.client.get(self.stock_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_stock_filter_by_product(self):
        self.authenticate_manager()

        response = self.client.get(self.stock_url, {'product': str(self.product.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['sku'] for item in self.response_items(response)], [self.variant.sku])

    def test_stock_filter_by_category(self):
        self.authenticate_manager()

        response = self.client.get(self.stock_url, {'category_slug': self.category.slug})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['sku'] for item in self.response_items(response)], [self.variant.sku])

    def test_stock_filter_by_size_and_color(self):
        self.authenticate_manager()

        response = self.client.get(
            self.stock_url,
            {'size': str(self.size_41.id), 'color': self.black.slug},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['sku'] for item in self.response_items(response)], [self.variant.sku])

    def test_stock_filter_by_brand_and_in_stock(self):
        self.authenticate_manager()

        response = self.client.get(
            self.stock_url,
            {'brand_slug': self.brand.slug, 'in_stock': 'true'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['sku'] for item in self.response_items(response)], [self.variant.sku])

    def test_manager_can_view_stock_movements(self):
        self.authenticate_manager()

        response = self.client.get(self.movements_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['sku'], self.variant.sku)
        self.assertEqual(items[0]['product']['slug'], self.product.slug)
        self.assertEqual(items[0]['user']['email'], self.manager.email)

    def test_stock_movement_filter_by_operation_type(self):
        self.authenticate_manager()

        response = self.client.get(
            self.movements_url,
            {'operation_type': StockMovement.OperationType.SALE},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = self.response_items(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['operation_type'], StockMovement.OperationType.SALE)

    def test_stock_movement_filter_by_sku(self):
        self.authenticate_manager()

        response = self.client.get(self.movements_url, {'sku': self.variant.sku})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.response_items(response)), 2)

    def test_manager_can_adjust_stock(self):
        self.authenticate_manager()

        response = self.client.post(
            self.stock_adjust_url,
            {
                'variant_id': self.variant.id,
                'new_quantity': 8,
                'comment': 'Inventory count',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)
        self.assertEqual(response.data['variant'], self.variant.id)
        self.assertEqual(response.data['sku'], self.variant.sku)
        self.assertEqual(response.data['quantity'], 3)
        self.assertEqual(response.data['operation_type'], StockMovement.OperationType.MANUAL_ADJUSTMENT)
        self.assertEqual(response.data['comment'], 'Inventory count')
        movement = StockMovement.objects.get(pk=response.data['id'])
        self.assertEqual(movement.user, self.manager)

    def test_stock_adjustment_uses_default_comment(self):
        self.authenticate_manager()

        response = self.client.post(
            self.stock_adjust_url,
            {
                'variant_id': self.variant.id,
                'new_quantity': 7,
                'comment': '',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['comment'], 'Manual adjustment to 7 via API')

    def test_customer_cannot_adjust_stock(self):
        self.client.force_authenticate(self.customer)

        response = self.client.post(
            self.stock_adjust_url,
            {'variant_id': self.variant.id, 'new_quantity': 8},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)

    def test_stock_adjustment_rejects_negative_quantity(self):
        self.authenticate_manager()
        movement_count = StockMovement.objects.count()

        response = self.client.post(
            self.stock_adjust_url,
            {'variant_id': self.variant.id, 'new_quantity': -1},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_stock_adjustment_rejects_unchanged_quantity(self):
        self.authenticate_manager()
        movement_count = StockMovement.objects.count()

        response = self.client.post(
            self.stock_adjust_url,
            {'variant_id': self.variant.id, 'new_quantity': 5},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_stock_adjustment_returns_404_for_unknown_variant(self):
        self.authenticate_manager()

        response = self.client.post(
            self.stock_adjust_url,
            {'variant_id': 999999, 'new_quantity': 8},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

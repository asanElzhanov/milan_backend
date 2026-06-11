from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Color, Product, ProductVariant, Size, StockMovement


class ProductAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='secret123',
        )
        self.client.force_login(self.admin_user)
        self.category = Category.objects.create(name='Shoes', slug='shoes')
        self.brand = Brand.objects.create(name='Nike', slug='nike')
        self.color = Color.objects.create(name='Black', slug='black', hex_code='#000000')
        self.size = Size.objects.create(value='42', size_type=Size.SizeType.SHOES)
        self.product = Product.objects.create(
            sku='SKU-ADMIN',
            name='Admin Product',
            slug='admin-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
            old_price=Decimal('120.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size=self.size,
            sku='VAR-ADMIN-42-BLACK',
            stock_quantity=3,
        )

    def test_product_changelist_opens(self):
        response = self.client.get(reverse('admin:catalog_product_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Product')

    def test_product_change_page_opens_with_inlines(self):
        response = self.client.get(reverse('admin:catalog_product_change', args=[self.product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAR-ADMIN-42-BLACK')
        self.assertContains(response, 'id_images-TOTAL_FORMS')
        self.assertContains(response, 'id_media-TOTAL_FORMS')

    def test_product_admin_searches_by_variant_sku(self):
        response = self.client.get(
            reverse('admin:catalog_product_changelist'),
            {'q': self.variant.sku},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Product')

    def test_product_admin_filters_by_stock(self):
        response = self.client.get(
            reverse('admin:catalog_product_changelist'),
            {'in_stock': 'yes'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Product')

    def test_product_variant_admin_opens_with_read_only_stock(self):
        response = self.client.get(reverse('admin:catalog_productvariant_change', args=[self.variant.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAR-ADMIN-42-BLACK')
        self.assertContains(response, 'Остаток')

    def test_stock_movement_admin_is_read_only(self):
        movement = StockMovement.objects.create(
            variant=self.variant,
            quantity=1,
            operation_type=StockMovement.OperationType.INCOME,
            user=self.admin_user,
            comment='Readonly history',
        )

        response = self.client.post(
            reverse('admin:catalog_stockmovement_change', args=[movement.pk]),
            {
                'variant': self.variant.pk,
                'quantity': 99,
                'operation_type': StockMovement.OperationType.SALE,
                'comment': 'Changed',
            },
        )

        self.assertEqual(response.status_code, 403)
        movement.refresh_from_db()
        self.assertEqual(movement.quantity, 1)
        self.assertEqual(movement.operation_type, StockMovement.OperationType.INCOME)
        self.assertEqual(movement.comment, 'Readonly history')

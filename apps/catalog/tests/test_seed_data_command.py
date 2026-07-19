from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Color, Product, ProductVariant, Size
from apps.orders.models import DeliveryMethod, Order, PromoCode


class SeedDataCommandTests(TestCase):
    def call_seed(self, *args):
        out = StringIO()
        call_command('seed_data', *args, stdout=out)
        return out.getvalue()

    def test_seed_data_runs_successfully(self):
        output = self.call_seed('--full')

        self.assertIn('seed_data completed', output)
        self.assertTrue(User.objects.filter(email='seed.admin@example.com').exists())
        self.assertTrue(User.objects.filter(email='seed.manager@example.com').exists())
        self.assertTrue(User.objects.filter(email='seed.customer@example.com').exists())

    def test_seed_data_twice_does_not_create_duplicates(self):
        self.call_seed('--full', '--with-demo-orders')
        first_counts = {
            'users': User.objects.filter(email__startswith='seed.').count(),
            'products': Product.objects.filter(sku__startswith='SEED-').count(),
            'variants': ProductVariant.objects.filter(sku__startswith='SEED-').count(),
            'orders': Order.objects.filter(order_number__startswith='SEED-ORDER-').count(),
            'promos': PromoCode.objects.filter(code__startswith='SEED').count(),
        }

        self.call_seed('--full', '--with-demo-orders')
        second_counts = {
            'users': User.objects.filter(email__startswith='seed.').count(),
            'products': Product.objects.filter(sku__startswith='SEED-').count(),
            'variants': ProductVariant.objects.filter(sku__startswith='SEED-').count(),
            'orders': Order.objects.filter(order_number__startswith='SEED-ORDER-').count(),
            'promos': PromoCode.objects.filter(code__startswith='SEED').count(),
        }

        self.assertEqual(second_counts, first_counts)

    def test_required_dictionaries_are_created(self):
        self.call_seed('--full')

        self.assertTrue(Category.objects.filter(slug='men').exists())
        self.assertTrue(Category.objects.filter(slug='women').exists())
        self.assertTrue(Category.objects.filter(slug='shoes').exists())
        self.assertTrue(Category.objects.filter(slug='accessories').exists())
        self.assertEqual(
            set(Brand.objects.filter(slug__in={'nike', 'adidas', 'puma', 'local-brand'}).values_list('slug', flat=True)),
            {'nike', 'adidas', 'puma', 'local-brand'},
        )
        self.assertEqual(Color.objects.filter(slug__in={'black', 'white', 'red', 'blue'}).count(), 4)
        self.assertTrue(Size.objects.filter(size_type=Size.SizeType.CLOTHES, value='M').exists())
        self.assertTrue(Size.objects.filter(size_type=Size.SizeType.SHOES, value='42').exists())
        self.assertTrue(Size.objects.filter(size_type=Size.SizeType.ACCESSORIES, value='One Size').exists())

    def test_demo_products_and_variants_are_created(self):
        self.call_seed('--full')

        self.assertGreaterEqual(Product.objects.filter(sku__startswith='SEED-', is_active=True).count(), 5)
        self.assertTrue(Product.objects.filter(sku='SEED-INACTIVE-001', is_active=False).exists())
        self.assertTrue(Product.objects.filter(sku='SEED-NIKE-AIR-001', old_price__gt=Decimal('0.00')).exists())
        self.assertTrue(Product.objects.filter(sku='SEED-NIKE-AIR-001', is_new=True).exists())
        self.assertGreaterEqual(ProductVariant.objects.filter(product__sku='SEED-NIKE-AIR-001').count(), 4)

    def test_delivery_methods_and_promo_codes_are_created(self):
        self.call_seed('--full')

        self.assertEqual(
            set(DeliveryMethod.objects.filter(code__in={'courier', 'pickup', 'kazakhstan_delivery'}).values_list('code', flat=True)),
            {'courier', 'pickup', 'kazakhstan_delivery'},
        )
        self.assertEqual(
            set(PromoCode.objects.filter(code__in={'SEED10', 'SEEDFIXED', 'SEEDEXPIRED', 'SEEDINACTIVE', 'SEEDMIN'}).values_list('code', flat=True)),
            {'SEED10', 'SEEDFIXED', 'SEEDEXPIRED', 'SEEDINACTIVE', 'SEEDMIN'},
        )

    def test_with_demo_orders_creates_orders(self):
        self.call_seed('--full', '--with-demo-orders')

        orders = Order.objects.filter(order_number__startswith='SEED-ORDER-')
        self.assertEqual(orders.count(), 3)
        self.assertTrue(orders.filter(status=Order.Status.COMPLETED).exists())
        self.assertTrue(orders.filter(status=Order.Status.CANCELLED).exists())
        self.assertTrue(orders.filter(items__isnull=False).distinct().count(), 3)

    def test_reset_removes_only_demo_data(self):
        Category.objects.create(name_ru='Real Category', slug='real-category')
        product = Product.objects.create(
            sku='REAL-SKU',
            name_ru='Real Product',
            slug='real-product',
            category=Category.objects.get(slug='real-category'),
            price=Decimal('100.00'),
        )

        self.call_seed('--full', '--with-demo-orders', '--with-demo-notifications')
        self.assertTrue(Order.objects.filter(order_number__startswith='SEED-ORDER-').exists())

        self.call_seed('--reset')

        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        self.assertFalse(Order.objects.filter(order_number__startswith='SEED-ORDER-').exists())
        self.assertTrue(Product.objects.filter(sku='SEED-NIKE-AIR-001').exists())

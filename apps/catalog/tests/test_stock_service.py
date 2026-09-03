from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.catalog.services import InvalidStockQuantityError, NotEnoughStockError, StockService


class StockServiceTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='nike')
        product = Product.objects.create(
            sku='SKU-STOCK-SERVICE',
            name_ru='Stock Service Product',
            slug='stock-service-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-STOCK-SERVICE',
            stock_quantity=10,
        )
        self.user = User.objects.create_user(email='stock-service@example.com')

    def refresh_variant(self):
        self.variant.refresh_from_db()
        return self.variant

    def assert_last_movement(self, operation_type, quantity):
        movement = StockMovement.objects.latest('created_at')
        self.assertEqual(movement.variant, self.variant)
        self.assertEqual(movement.operation_type, operation_type)
        self.assertEqual(movement.quantity, quantity)
        return movement

    def test_check_availability_requires_active_variant_and_enough_stock(self):
        self.assertTrue(StockService.check_availability(self.variant, 10))
        self.assertFalse(StockService.check_availability(self.variant, 11))

        self.variant.is_active = False
        self.variant.save(update_fields=['is_active'])

        self.assertFalse(StockService.check_availability(self.variant.pk, 1))

    def test_check_availability_rejects_invalid_quantity(self):
        with self.assertRaises(InvalidStockQuantityError):
            StockService.check_availability(self.variant, 0)

    def test_income_increases_stock_and_creates_movement(self):
        StockService.income(self.variant, 5, user=self.user, comment='Receipt')

        self.assertEqual(self.refresh_variant().stock_quantity, 15)
        movement = self.assert_last_movement(StockMovement.OperationType.INCOME, 5)
        self.assertEqual(movement.user, self.user)
        self.assertEqual(movement.comment, 'Receipt')

    def test_sale_decreases_stock_and_creates_movement(self):
        StockService.sale(self.variant.pk, 4, user=self.user, comment='Sale')

        self.assertEqual(self.refresh_variant().stock_quantity, 6)
        movement = self.assert_last_movement(StockMovement.OperationType.SALE, 4)
        self.assertEqual(movement.user, self.user)

    def test_sale_does_not_allow_negative_stock_and_does_not_create_movement(self):
        with self.assertRaises(NotEnoughStockError):
            StockService.sale(self.variant, 11)

        self.assertEqual(self.refresh_variant().stock_quantity, 10)
        self.assertFalse(StockMovement.objects.exists())

    def test_sale_requires_active_variant(self):
        self.variant.is_active = False
        self.variant.save(update_fields=['is_active'])

        with self.assertRaises(NotEnoughStockError):
            StockService.sale(self.variant, 1)

        self.assertEqual(self.refresh_variant().stock_quantity, 10)
        self.assertFalse(StockMovement.objects.exists())

    def test_return_stock_increases_stock_and_creates_movement(self):
        StockService.return_stock(self.variant, 2)

        self.assertEqual(self.refresh_variant().stock_quantity, 12)
        self.assert_last_movement(StockMovement.OperationType.RETURN, 2)

    def test_cancel_order_increases_stock_and_creates_movement(self):
        StockService.cancel_order(self.variant, 3)

        self.assertEqual(self.refresh_variant().stock_quantity, 13)
        self.assert_last_movement(StockMovement.OperationType.ORDER_CANCEL, 3)

    def test_manual_adjustment_sets_new_stock_and_creates_movement(self):
        StockService.manual_adjustment(self.variant, 4, user=self.user, comment='Inventory count')

        self.assertEqual(self.refresh_variant().stock_quantity, 4)
        movement = self.assert_last_movement(StockMovement.OperationType.MANUAL_ADJUSTMENT, 6)
        self.assertEqual(movement.comment, 'Inventory count')

    def test_manual_adjustment_rejects_negative_stock_and_does_not_create_movement(self):
        with self.assertRaises(InvalidStockQuantityError):
            StockService.manual_adjustment(self.variant, -1)

        self.assertEqual(self.refresh_variant().stock_quantity, 10)
        self.assertFalse(StockMovement.objects.exists())

    def test_manual_adjustment_rejects_unchanged_stock_and_does_not_create_movement(self):
        with self.assertRaises(InvalidStockQuantityError):
            StockService.manual_adjustment(self.variant, 10)

        self.assertEqual(self.refresh_variant().stock_quantity, 10)
        self.assertFalse(StockMovement.objects.exists())

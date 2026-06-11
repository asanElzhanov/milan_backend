from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement


class StockMovementModelTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Shoes', slug='shoes')
        brand = Brand.objects.create(name='Nike', slug='nike')
        product = Product.objects.create(
            sku='SKU-STOCK',
            name='Stock Product',
            slug='stock-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-STOCK',
            stock_quantity=10,
        )
        self.user = User.objects.create_user(email='stock@example.com')

    def test_creates_stock_movement(self):
        movement = StockMovement.objects.create(
            variant=self.variant,
            quantity=3,
            operation_type=StockMovement.OperationType.INCOME,
            user=self.user,
            comment='Initial receipt',
        )

        self.assertEqual(movement.variant, self.variant)
        self.assertEqual(movement.quantity, 3)
        self.assertEqual(movement.user, self.user)
        self.assertEqual(self.variant.stock_movements.get(), movement)
        self.assertIn('VAR-STOCK', str(movement))

    def test_quantity_must_be_positive(self):
        movement = StockMovement(
            variant=self.variant,
            quantity=0,
            operation_type=StockMovement.OperationType.SALE,
        )

        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_operation_type_must_be_from_choices(self):
        movement = StockMovement(
            variant=self.variant,
            quantity=1,
            operation_type='unknown',
        )

        with self.assertRaises(ValidationError):
            movement.full_clean()

    def test_stock_movement_does_not_change_variant_stock_directly(self):
        StockMovement.objects.create(
            variant=self.variant,
            quantity=4,
            operation_type=StockMovement.OperationType.SALE,
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)

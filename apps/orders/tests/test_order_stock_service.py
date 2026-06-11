from decimal import Decimal

from django.test import TestCase

from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.models import Cart, CartItem, Order
from apps.orders.serializers import OrderCreateSerializer


class OrderStockServiceTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Shoes', slug='shoes')
        brand = Brand.objects.create(name='Nike', slug='nike')
        product = Product.objects.create(
            sku='SKU-ORDER-STOCK',
            name='Order Stock Product',
            slug='order-stock-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-ORDER-STOCK',
            stock_quantity=5,
        )
        self.cart = Cart.objects.create()
        CartItem.objects.create(cart=self.cart, variant=self.variant, quantity=2)

    def test_order_create_decreases_stock_through_stock_service(self):
        serializer = OrderCreateSerializer(
            data={
                'first_name': 'Customer',
                'email': 'customer@example.com',
                'phone': '+77011234567',
                'delivery_method': Order.DeliveryMethod.PICKUP,
            },
            context={'cart': self.cart, 'user': None},
        )
        serializer.is_valid(raise_exception=True)

        order = serializer.save()

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)
        movement = StockMovement.objects.get()
        self.assertEqual(movement.variant, self.variant)
        self.assertEqual(movement.quantity, 2)
        self.assertEqual(movement.operation_type, StockMovement.OperationType.SALE)
        self.assertIn(order.order_number, movement.comment)

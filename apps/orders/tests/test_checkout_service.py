from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Color, Product, ProductVariant, Size, StockMovement
from apps.orders.models import Cart, CartItem, DeliveryMethod, Order, OrderItem, OrderStatusHistory
from apps.orders.services import CheckoutService, EmptyCartError, InvalidCheckoutDataError, NotEnoughStockError


class CheckoutServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shoes', slug='checkout-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='checkout-nike')
        self.color = Color.objects.create(name='Black', slug='checkout-black', hex_code='#000000')
        self.size = Size.objects.create(value='42', size_type=Size.SizeType.SHOES, sort_order=1)
        self.product = Product.objects.create(
            sku='SKU-CHECKOUT',
            name='Checkout Product',
            slug='checkout-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size=self.size,
            sku='VAR-CHECKOUT',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.second_variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-CHECKOUT-SECOND',
            stock_quantity=3,
        )
        self.user = User.objects.create_user(email='checkout@example.com')
        self.courier_delivery = DeliveryMethod.objects.get(code='courier')
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])

    def create_cart(self):
        cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=2)
        CartItem.objects.create(cart=cart, variant=self.second_variant, quantity=1)
        return cart

    def checkout(self, cart):
        return CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            comment='Leave at reception',
        )

    def test_checkout_creates_order_items_and_snapshots(self):
        cart = self.create_cart()

        order = self.checkout(cart)

        self.assertEqual(order.user, self.user)
        self.assertTrue(order.order_number.startswith('ORD-'))
        self.assertEqual(order.customer_name, 'Customer Name')
        self.assertEqual(order.delivery_method_ref, self.courier_delivery)
        self.assertEqual(order.delivery_method, 'courier')
        self.assertEqual(order.delivery_method_code, 'courier')
        self.assertEqual(order.delivery_method_name, 'Курьерская доставка')
        self.assertEqual(order.items_total, Decimal('340.00'))
        self.assertEqual(order.delivery_price, Decimal('1000.00'))
        self.assertFalse(order.delivery_requires_manager_calculation)
        self.assertTrue(order.delivery_price_is_final)
        self.assertEqual(order.total_amount, Decimal('1340.00'))
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

        items = list(order.items.order_by('id'))
        self.assertEqual(len(items), 2)
        first_item = items[0]
        self.assertEqual(first_item.variant, self.variant)
        self.assertEqual(first_item.product_name, 'Checkout Product')
        self.assertEqual(first_item.product_slug, 'checkout-product')
        self.assertEqual(first_item.sku, 'VAR-CHECKOUT')
        self.assertEqual(first_item.size_name, '42')
        self.assertEqual(first_item.color_name, 'Black')
        self.assertEqual(first_item.unit_price, Decimal('120.00'))
        self.assertEqual(first_item.quantity, 2)
        self.assertEqual(first_item.total_price, Decimal('240.00'))

    def test_checkout_writes_off_stock_creates_movement_and_clears_cart(self):
        cart = self.create_cart()

        order = self.checkout(cart)

        self.variant.refresh_from_db()
        self.second_variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)
        self.assertEqual(self.second_variant.stock_quantity, 2)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

        movements = list(StockMovement.objects.order_by('id'))
        self.assertEqual(len(movements), 2)
        self.assertEqual(movements[0].operation_type, StockMovement.OperationType.SALE)
        self.assertEqual(movements[0].quantity, 2)
        self.assertIn(order.order_number, movements[0].comment)

    def test_checkout_marks_manager_delivery_price_as_not_final(self):
        delivery = DeliveryMethod.objects.get(code='kazakhstan_delivery')
        delivery.price_type = DeliveryMethod.PriceType.MANAGER_CALCULATION
        delivery.save(update_fields=['price_type', 'updated_at'])
        cart = self.create_cart()

        order = CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method='kazakhstan_delivery',
        )

        self.assertEqual(order.delivery_method_ref, delivery)
        self.assertEqual(order.delivery_price, Decimal('0.00'))
        self.assertTrue(order.delivery_requires_manager_calculation)
        self.assertFalse(order.delivery_price_is_final)
        self.assertEqual(order.total_amount, Decimal('340.00'))

    def test_checkout_with_pickup_allows_blank_address_and_free_delivery(self):
        delivery = DeliveryMethod.objects.get(code='pickup')
        delivery.price_type = DeliveryMethod.PriceType.FREE
        delivery.base_price = Decimal('0.00')
        delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])
        cart = self.create_cart()

        order = CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='',
            delivery_method='pickup',
        )

        self.assertEqual(order.delivery_method_code, 'pickup')
        self.assertEqual(order.items_total, Decimal('340.00'))
        self.assertEqual(order.delivery_price, Decimal('0.00'))
        self.assertFalse(order.delivery_requires_manager_calculation)
        self.assertEqual(order.total_amount, Decimal('340.00'))

    def test_checkout_with_free_from_amount_makes_delivery_free(self):
        self.courier_delivery.free_from_amount = Decimal('300.00')
        self.courier_delivery.save(update_fields=['free_from_amount', 'updated_at'])
        cart = self.create_cart()

        order = self.checkout(cart)

        self.assertEqual(order.items_total, Decimal('340.00'))
        self.assertEqual(order.delivery_price, Decimal('0.00'))
        self.assertEqual(order.total_amount, Decimal('340.00'))

    def test_checkout_rejects_courier_without_delivery_address(self):
        cart = self.create_cart()

        with self.assertRaises(InvalidCheckoutDataError):
            CheckoutService.checkout(
                cart=cart,
                user=self.user,
                customer_name='Customer Name',
                phone='+77011234567',
                email='customer@example.com',
                city='Almaty',
                delivery_address='',
                delivery_method='courier',
            )

        self.assertFalse(Order.objects.exists())

    def test_checkout_accepts_delivery_method_id(self):
        cart = self.create_cart()

        order = CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Customer Name',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=self.courier_delivery.id,
        )

        self.assertEqual(order.delivery_method_ref, self.courier_delivery)
        self.assertEqual(order.delivery_method_code, self.courier_delivery.code)

    def test_checkout_rejects_inactive_delivery_method(self):
        self.courier_delivery.is_active = False
        self.courier_delivery.save(update_fields=['is_active', 'updated_at'])
        cart = self.create_cart()

        with self.assertRaises(InvalidCheckoutDataError):
            self.checkout(cart)

        self.assertFalse(Order.objects.exists())

    def test_checkout_creates_initial_status_history(self):
        cart = self.create_cart()

        order = self.checkout(cart)

        history = OrderStatusHistory.objects.get(order=order)
        self.assertIsNone(history.old_status)
        self.assertEqual(history.new_status, Order.Status.NEW)
        self.assertIsNone(history.changed_by)

    def test_checkout_rejects_empty_cart(self):
        cart = Cart.objects.create(user=self.user, token=None)

        with self.assertRaises(EmptyCartError):
            self.checkout(cart)

        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_not_enough_stock_without_side_effects(self):
        cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=6)

        with self.assertRaises(NotEnoughStockError):
            self.checkout(cart)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertTrue(CartItem.objects.filter(cart=cart).exists())
        self.assertFalse(Order.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_checkout_rolls_back_if_stock_write_off_fails_after_order_item(self):
        cart = self.create_cart()

        with patch('apps.orders.services.StockService.sale', side_effect=ValidationError('boom')):
            with self.assertRaises(ValidationError):
                self.checkout(cart)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertTrue(CartItem.objects.filter(cart=cart).exists())
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_second_checkout_cannot_take_stock_below_zero(self):
        first_cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=first_cart, variant=self.variant, quantity=4)
        self.checkout(first_cart)

        second_cart = Cart.objects.create(token=None)
        CartItem.objects.create(cart=second_cart, variant=self.variant, quantity=2)

        with self.assertRaises(NotEnoughStockError):
            CheckoutService.checkout(
                cart=second_cart,
                user=None,
                customer_name='Guest',
                phone='+77017654321',
                email='guest@example.com',
                city='Almaty',
                delivery_address='Satpayev 1',
                delivery_method=Order.DeliveryMethod.PICKUP,
            )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertTrue(CartItem.objects.filter(cart=second_cart).exists())

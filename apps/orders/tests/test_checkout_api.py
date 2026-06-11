from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.models import CartItem, Order
from apps.orders.services import CartService


class CheckoutApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name='Shoes', slug='checkout-api-shoes')
        brand = Brand.objects.create(name='Nike', slug='checkout-api-nike')
        self.product = Product.objects.create(
            sku='SKU-CHECKOUT-API',
            name='Checkout API Product',
            slug='checkout-api-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-CHECKOUT-API',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.user = User.objects.create_user(email='checkout-api@example.com')

    def checkout_url(self):
        return '/api/v1/orders/checkout/'

    def payload(self, **overrides):
        data = {
            'customer_name': 'Customer Name',
            'phone': '+77011234567',
            'email': 'customer@example.com',
            'city': 'Almaty',
            'delivery_address': 'Abay 10',
            'delivery_method': Order.DeliveryMethod.COURIER,
            'comment': 'Leave at reception',
        }
        data.update(overrides)
        return data

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_user_can_checkout_own_cart(self, _send_email):
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('order_number', response.data)
        self.assertEqual(response.data['customer_name'], 'Customer Name')
        self.assertEqual(response.data['status'], Order.Status.NEW)
        self.assertEqual(response.data['payment_status'], Order.PaymentStatus.UNPAID)
        self.assertEqual(response.data['total_amount'], '240.00')
        self.assertEqual(len(response.data['items']), 1)
        self.assertEqual(response.data['items'][0]['sku'], self.variant.sku)

        order = Order.objects.get(order_number=response.data['order_number'])
        self.assertEqual(order.user, self.user)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)
        self.assertEqual(StockMovement.objects.count(), 1)

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_guest_can_checkout_by_body_cart_token(self, _send_email):
        cart = CartService.get_or_create_guest_cart()
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(cart_token=str(cart.token)),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(order_number=response.data['order_number'])
        self.assertIsNone(order.user)
        self.assertEqual(response.data['total_amount'], '120.00')
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    def test_guest_without_cart_token_cannot_checkout(self):
        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_empty_cart(self):
        self.client.force_authenticate(user=self.user)
        CartService.get_or_create_user_cart(self.user)

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_not_enough_stock(self):
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)
        self.variant.stock_quantity = 1
        self.variant.save(update_fields=['stock_quantity'])

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CartItem.objects.filter(cart=cart).exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)

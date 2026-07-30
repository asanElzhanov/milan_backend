from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import Cart, CartItem, Order
from apps.orders.services import CheckoutService, OrderStatusService


class OrderCancelApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='cancel-shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='cancel-nike')
        product = Product.objects.create(
            sku='SKU-CANCEL',
            name_ru='Cancel Product',
            slug='cancel-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-CANCEL',
            stock_quantity=10,
        )
        self.user = User.objects.create_user(email='cancel@example.com')
        self.other_user = User.objects.create_user(email='other-cancel@example.com')

    def create_order(self, user=None, quantity=2, email='customer@example.com'):
        cart = Cart.objects.create(user=user, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=quantity)
        return CheckoutService.checkout(
            cart=cart,
            user=user,
            customer_name='Customer',
            phone='+77011234567',
            email=email,
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
        )

    def cancel_url(self, order):
        return f'/api/v1/orders/{order.order_number}/cancel/'

    def test_owner_can_cancel_and_stock_is_returned(self):
        order = self.create_order(user=self.user, quantity=3)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 7)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.cancel_url(order), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.CANCELLED)
        self.assertEqual(response.data['payment_status'], Order.PaymentStatus.CANCELLED)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_other_user_cannot_cancel(self):
        order = self.create_order(user=self.user)
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(self.cancel_url(order), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_guest_can_cancel_with_matching_email(self):
        order = self.create_order(user=None, email='guest@example.com')

        response = self.client.post(
            self.cancel_url(order), {'email': 'guest@example.com'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_guest_wrong_email_is_forbidden(self):
        order = self.create_order(user=None, email='guest@example.com')

        response = self.client.post(
            self.cancel_url(order), {'email': 'wrong@example.com'}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_paid_order_cannot_be_cancelled_online(self):
        order = self.create_order(user=self.user)
        OrderStatusService.mark_paid(order)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.cancel_url(order), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_cancelling_already_cancelled_is_idempotent(self):
        order = self.create_order(user=self.user)
        OrderStatusService.cancel_order(order)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.cancel_url(order), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.CANCELLED)

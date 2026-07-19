from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import Order, OrderItem, OrderStatusHistory


class OrderHistoryApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='history-shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='history-nike')
        product = Product.objects.create(
            sku='SKU-HISTORY',
            name_ru='History Product',
            slug='history-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-HISTORY',
            stock_quantity=5,
        )
        self.user = User.objects.create_user(email='history@example.com')
        self.other_user = User.objects.create_user(email='other-history@example.com')
        self.order = self.create_order(self.user, Order.Status.NEW, 'Customer One')
        self.processing_order = self.create_order(self.user, Order.Status.PROCESSING, 'Customer Two')
        self.other_order = self.create_order(self.other_user, Order.Status.NEW, 'Other Customer')

    def create_order(self, user, order_status, customer_name):
        order = Order.objects.create(
            user=user,
            customer_name=customer_name,
            phone='+77011234567',
            email=user.email,
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('200.00'),
            status=order_status,
            payment_status=Order.PaymentStatus.UNPAID,
            comment='Test comment',
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name='History Product',
            product_slug='history-product',
            sku='VAR-HISTORY',
            size_name='42',
            color_name='Black',
            unit_price=Decimal('100.00'),
            quantity=2,
            total_price=Decimal('200.00'),
        )
        OrderStatusHistory.objects.create(
            order=order,
            old_status=None,
            new_status=order_status,
            changed_by=user,
            comment='Initial status',
        )
        return order

    def orders_url(self):
        return '/api/v1/orders/'

    def detail_url(self, order):
        return f'/api/v1/orders/{order.order_number}/'

    def response_results(self, response):
        if isinstance(response.data, dict) and 'results' in response.data:
            return response.data['results']
        return response.data

    def test_user_sees_only_own_orders(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.orders_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.response_results(response)
        order_numbers = {item['order_number'] for item in results}
        self.assertEqual(order_numbers, {self.order.order_number, self.processing_order.order_number})
        self.assertNotIn(self.other_order.order_number, order_numbers)
        self.assertIn('items_count', results[0])

    def test_anonymous_user_cannot_list_orders(self):
        response = self.client.get(self.orders_url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_open_order_detail_by_order_number(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.detail_url(self.order))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['order_number'], self.order.order_number)
        self.assertEqual(response.data['customer_name'], 'Customer One')
        self.assertEqual(len(response.data['items']), 1)
        self.assertEqual(response.data['items'][0]['product_name'], 'History Product')
        self.assertEqual(len(response.data['status_history']), 1)
        self.assertEqual(response.data['status_history'][0]['new_status'], Order.Status.NEW)

    def test_user_cannot_open_other_user_order_detail(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.detail_url(self.other_order))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_status_filter_applies_to_current_user_orders_only(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.orders_url(), {'status': Order.Status.PROCESSING})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.response_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['order_number'], self.processing_order.order_number)
        self.assertEqual(results[0]['status'], Order.Status.PROCESSING)

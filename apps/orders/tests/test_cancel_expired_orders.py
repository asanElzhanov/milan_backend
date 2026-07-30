from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import Cart, CartItem, Order
from apps.orders.services import CheckoutService, OrderStatusService
from apps.orders.tasks import cancel_expired_orders, cancel_unpaid_order


@override_settings(ORDER_PAYMENT_TIMEOUT_MINUTES=30)
class CancelExpiredOrdersTaskTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='expire-shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='expire-nike')
        product = Product.objects.create(
            sku='SKU-EXPIRE',
            name_ru='Expire Product',
            slug='expire-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-EXPIRE',
            stock_quantity=10,
        )
        self.user = User.objects.create_user(email='expire@example.com')

    def create_order(self, quantity=2):
        cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=quantity)
        return CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Customer',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
        )

    def _backdate(self, order, minutes):
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes)
        )

    def test_expired_unpaid_order_is_cancelled_and_stock_returned(self):
        order = self.create_order(quantity=2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)
        self._backdate(order, minutes=45)

        result = cancel_expired_orders()

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.EXPIRED)
        self.assertEqual(self.variant.stock_quantity, 10)
        self.assertEqual(result['cancelled'], 1)

    def test_recent_order_is_not_cancelled(self):
        order = self.create_order()
        self._backdate(order, minutes=5)

        cancel_expired_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_paid_order_is_not_cancelled(self):
        order = self.create_order()
        OrderStatusService.mark_paid(order)
        self._backdate(order, minutes=90)

        cancel_expired_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    @override_settings(ORDER_PAYMENT_TIMEOUT_MINUTES=0)
    def test_disabled_when_timeout_is_zero(self):
        order = self.create_order()
        self._backdate(order, minutes=120)

        result = cancel_expired_orders()

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertEqual(result['status'], 'disabled')

    def test_scheduled_task_cancels_unpaid_order(self):
        order = self.create_order(quantity=2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 8)

        result = cancel_unpaid_order(order.id)

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.EXPIRED)
        self.assertEqual(self.variant.stock_quantity, 10)

    def test_scheduled_task_skips_paid_order(self):
        order = self.create_order()
        OrderStatusService.mark_paid(order)

        result = cancel_unpaid_order(order.id)

        order.refresh_from_db()
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_scheduled_task_handles_missing_order(self):
        result = cancel_unpaid_order(999999)
        self.assertEqual(result['status'], 'not_found')

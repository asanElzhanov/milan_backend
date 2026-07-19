from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.models import Cart, CartItem, Order, OrderStatusHistory
from apps.orders.services import (
    CheckoutService,
    InvalidOrderStatusTransitionError,
    OrderStatusService,
)


class OrderStatusServiceTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='status-shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='status-nike')
        product = Product.objects.create(
            sku='SKU-STATUS',
            name_ru='Status Product',
            slug='status-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-STATUS',
            stock_quantity=5,
        )
        self.user = User.objects.create_user(email='status@example.com')
        self.manager = User.objects.create_user(email='manager@example.com')

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

    def test_change_status_updates_order_and_creates_history(self):
        order = self.create_order()

        updated_order = OrderStatusService.change_status(
            order,
            Order.Status.WAITING_PAYMENT,
            changed_by=self.manager,
            comment='Invoice sent',
        )

        self.assertEqual(updated_order.status, Order.Status.WAITING_PAYMENT)
        history = OrderStatusHistory.objects.latest('created_at')
        self.assertEqual(history.order, updated_order)
        self.assertEqual(history.old_status, Order.Status.NEW)
        self.assertEqual(history.new_status, Order.Status.WAITING_PAYMENT)
        self.assertEqual(history.changed_by, self.manager)
        self.assertEqual(history.comment, 'Invoice sent')

    def test_same_status_does_not_create_extra_history(self):
        order = self.create_order()
        initial_history_count = OrderStatusHistory.objects.filter(order=order).count()

        updated_order = OrderStatusService.change_status(order, Order.Status.NEW)

        self.assertEqual(updated_order.status, Order.Status.NEW)
        self.assertEqual(OrderStatusHistory.objects.filter(order=order).count(), initial_history_count)

    def test_invalid_transition_is_rejected(self):
        order = self.create_order()

        with self.assertRaises(InvalidOrderStatusTransitionError):
            OrderStatusService.change_status(order, Order.Status.SHIPPED)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_cancel_order_returns_stock_and_writes_history(self):
        order = self.create_order(quantity=2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

        cancelled_order = OrderStatusService.cancel_order(
            order,
            changed_by=self.manager,
            comment='Customer cancelled',
        )

        self.variant.refresh_from_db()
        self.assertEqual(cancelled_order.status, Order.Status.CANCELLED)
        self.assertEqual(cancelled_order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(self.variant.stock_quantity, 5)

        movement = StockMovement.objects.latest('created_at')
        self.assertEqual(movement.operation_type, StockMovement.OperationType.ORDER_CANCEL)
        self.assertEqual(movement.quantity, 2)
        self.assertEqual(movement.user, self.manager)
        self.assertIn(order.order_number, movement.comment)

        history = OrderStatusHistory.objects.latest('created_at')
        self.assertEqual(history.old_status, Order.Status.NEW)
        self.assertEqual(history.new_status, Order.Status.CANCELLED)
        self.assertEqual(history.changed_by, self.manager)
        self.assertEqual(history.comment, 'Customer cancelled')

    def test_cancelled_order_cannot_move_to_processing(self):
        order = self.create_order()
        cancelled_order = OrderStatusService.cancel_order(order)

        with self.assertRaises(InvalidOrderStatusTransitionError):
            OrderStatusService.change_status(cancelled_order, Order.Status.PROCESSING)

    def test_completed_order_can_be_returned(self):
        order = self.create_order()
        order = OrderStatusService.mark_paid(order)
        order = OrderStatusService.change_status(order, Order.Status.PROCESSING)
        order = OrderStatusService.change_status(order, Order.Status.SHIPPED)
        order = OrderStatusService.change_status(order, Order.Status.COMPLETED)

        returned_order = OrderStatusService.change_status(
            order,
            Order.Status.RETURNED,
            changed_by=self.manager,
        )

        self.assertEqual(returned_order.status, Order.Status.RETURNED)
        history = OrderStatusHistory.objects.latest('created_at')
        self.assertEqual(history.old_status, Order.Status.COMPLETED)
        self.assertEqual(history.new_status, Order.Status.RETURNED)
        self.assertEqual(history.changed_by, self.manager)

    def test_mark_paid_updates_payment_status_and_order_status(self):
        order = self.create_order()

        paid_order = OrderStatusService.mark_paid(
            order,
            changed_by=self.manager,
            comment='Payment webhook',
        )

        self.assertEqual(paid_order.status, Order.Status.PAID)
        self.assertEqual(paid_order.payment_status, Order.PaymentStatus.PAID)
        history = OrderStatusHistory.objects.latest('created_at')
        self.assertEqual(history.old_status, Order.Status.NEW)
        self.assertEqual(history.new_status, Order.Status.PAID)
        self.assertEqual(history.changed_by, self.manager)
        self.assertEqual(history.comment, 'Payment webhook')

import shutil
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, ImportJob, Product, ProductVariant
from apps.catalog.services import ProductReviewService, StockService
from apps.catalog.tasks import process_product_import
from apps.notifications.models import Notification
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.orders.services import CheckoutService, OrderStatusService
from apps.payments.models import Payment
from apps.payments.views import StripeWebhookView


@override_settings(LOW_STOCK_THRESHOLD=3)
class StaffNotificationFlowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.manager = User.objects.create_user(
            email='staff-manager@example.com',
            role=User.Role.MANAGER,
        )
        self.admin = User.objects.create_user(
            email='staff-admin@example.com',
            role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(email='staff-customer@example.com')
        self.category = Category.objects.create(name='Shoes', slug='staff-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='staff-nike')
        self.product = Product.objects.create(
            sku='SKU-STAFF',
            name='Staff Product',
            slug='staff-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-STAFF',
            stock_quantity=10,
        )

    def create_order(self, *, status=Order.Status.NEW, payment_status=Order.PaymentStatus.UNPAID):
        order = Order.objects.create(
            user=self.customer,
            customer_name='Staff Customer',
            phone='+77011234567',
            email='staff-customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            items_total=Decimal('100.00'),
            delivery_price=Decimal('0.00'),
            total_amount=Decimal('100.00'),
            status=status,
            payment_status=payment_status,
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name=self.product.name,
            product_slug=self.product.slug,
            sku=self.variant.sku,
            unit_price=Decimal('100.00'),
            quantity=1,
            total_price=Decimal('100.00'),
        )
        return order

    def assert_staff_notified(self, event_type):
        notifications = Notification.objects.filter(event_type=event_type)
        recipients = {notification.recipient for notification in notifications}
        self.assertIn(self.manager, recipients)
        self.assertIn(self.admin, recipients)
        return notifications

    def test_new_order_creates_manager_admin_notification(self):
        cart = Cart.objects.create(user=self.customer, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)

        with patch('apps.notifications.tasks.send_order_created_email.delay'):
            with self.captureOnCommitCallbacks(execute=True):
                CheckoutService.checkout(
                    cart=cart,
                    user=self.customer,
                    customer_name='Staff Customer',
                    phone='+77011234567',
                    email='staff-customer@example.com',
                    city='Almaty',
                    delivery_address='Abay 10',
                    delivery_method=Order.DeliveryMethod.COURIER,
                )

        notifications = self.assert_staff_notified(Notification.EventType.ORDER_CREATED)
        self.assertTrue(notifications.filter(title__contains='Новый заказ').exists())

    def test_successful_payment_creates_notification(self):
        order = self.create_order()

        with patch('apps.notifications.tasks.send_order_paid_email.delay'):
            with self.captureOnCommitCallbacks(execute=True):
                OrderStatusService.mark_paid(order)

        notifications = self.assert_staff_notified(Notification.EventType.PAYMENT_SUCCESS)
        self.assertTrue(notifications.filter(message__contains=order.order_number).exists())

    def test_payment_error_creates_notification(self):
        order = self.create_order()
        payment = Payment.objects.create(
            order=order,
            provider=Payment.Provider.STRIPE,
            status=Payment.Status.PENDING,
            amount=order.total_amount,
            provider_payment_id='pi_staff_failed',
        )

        with self.captureOnCommitCallbacks(execute=True):
            StripeWebhookView()._handle_payment_failed(payment.provider_payment_id)

        notifications = self.assert_staff_notified(Notification.EventType.PAYMENT_ERROR)
        self.assertTrue(notifications.filter(message__contains='Stripe payment failed').exists())

    def test_new_pending_review_creates_notification(self):
        order = self.create_order(status=Order.Status.COMPLETED, payment_status=Order.PaymentStatus.PAID)

        with self.captureOnCommitCallbacks(execute=True):
            ProductReviewService.create_review(
                user=self.customer,
                product=self.product,
                order=order,
                rating=5,
                text='Great',
            )

        notifications = self.assert_staff_notified(Notification.EventType.REVIEW_CREATED)
        self.assertTrue(notifications.filter(message__contains=self.product.name).exists())

    def test_low_stock_notification_is_created_only_when_threshold_is_crossed(self):
        self.variant.stock_quantity = 5
        self.variant.save(update_fields=['stock_quantity'])

        with self.captureOnCommitCallbacks(execute=True):
            StockService.sale(self.variant, 2)
        self.assert_staff_notified(Notification.EventType.LOW_STOCK)
        initial_count = Notification.objects.filter(event_type=Notification.EventType.LOW_STOCK).count()

        with self.captureOnCommitCallbacks(execute=True):
            StockService.sale(self.variant, 1)

        self.assertEqual(
            Notification.objects.filter(event_type=Notification.EventType.LOW_STOCK).count(),
            initial_count,
        )

    def test_import_error_creates_notification(self):
        import_job = ImportJob.objects.create(
            file=SimpleUploadedFile(
                'broken-products.csv',
                b'product_name,price,sku\nBroken,100.00,BROKEN-SKU\n',
                content_type='text/csv',
            ),
            created_by=self.manager,
            status=ImportJob.Status.PENDING,
        )

        process_product_import.apply(args=(import_job.pk,), throw=True)

        notifications = self.assert_staff_notified(Notification.EventType.IMPORT_ERROR)
        self.assertTrue(notifications.filter(message__contains='Отсутствуют обязательные колонки').exists())

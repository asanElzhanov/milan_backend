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
from apps.payments import freedompay
from apps.payments.models import Payment


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
        self.category = Category.objects.create(name_ru='Shoes', slug='staff-shoes')
        self.brand = Brand.objects.create(name_ru='Nike', slug='staff-nike')
        self.product = Product.objects.create(
            sku='SKU-STAFF',
            name_ru='Staff Product',
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
            product_name=self.product.name_ru,
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

    @override_settings(FREEDOMPAY_SECRET_KEY='staff_secret')
    def test_payment_error_creates_notification(self):
        order = self.create_order()
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.FREEDOM,
            status=Payment.Status.PENDING,
            amount=order.total_amount,
            provider_payment_id='pay_staff_failed',
        )

        params = {
            'pg_order_id': order.order_number,
            'pg_payment_id': 'pay_staff_failed',
            'pg_result': '0',
            'pg_failure_description': 'FreedomPay payment failed.',
            'pg_salt': 'salt',
        }
        params['pg_sig'] = freedompay.generate_signature(
            freedompay.RESULT_SCRIPT, params, 'staff_secret'
        )

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post('/api/v1/payments/freedom/result', params)

        notifications = self.assert_staff_notified(Notification.EventType.PAYMENT_ERROR)
        self.assertTrue(notifications.filter(message__contains='FreedomPay payment failed').exists())

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
        self.assertTrue(notifications.filter(message__contains=self.product.name_ru).exists())

    def test_sale_that_crosses_below_threshold_creates_low_stock_notification(self):
        self.variant.stock_quantity = 5
        self.variant.save(update_fields=['stock_quantity'])

        with self.captureOnCommitCallbacks(execute=True):
            StockService.sale(self.variant, 3)

        notifications = self.assert_staff_notified(Notification.EventType.LOW_STOCK)
        message = notifications.first().message
        self.assertIn(self.product.name_ru, message)
        self.assertIn(self.variant.sku, message)
        self.assertIn('Текущий остаток: 2', message)
        self.assertIn('Порог: 3', message)

    def test_sale_that_stays_above_threshold_does_not_create_low_stock_notification(self):
        self.variant.stock_quantity = 5
        self.variant.save(update_fields=['stock_quantity'])

        with self.captureOnCommitCallbacks(execute=True):
            StockService.sale(self.variant, 1)

        self.assertFalse(Notification.objects.filter(event_type=Notification.EventType.LOW_STOCK).exists())

    def test_repeated_operation_below_threshold_does_not_spam_low_stock_notifications(self):
        self.variant.stock_quantity = 5
        self.variant.save(update_fields=['stock_quantity'])

        with self.captureOnCommitCallbacks(execute=True):
            StockService.sale(self.variant, 3)
        initial_count = Notification.objects.filter(event_type=Notification.EventType.LOW_STOCK).count()

        with self.captureOnCommitCallbacks(execute=True):
            StockService.sale(self.variant, 1)

        self.assertEqual(
            Notification.objects.filter(event_type=Notification.EventType.LOW_STOCK).count(),
            initial_count,
        )

    def test_manual_adjustment_below_threshold_creates_low_stock_notification(self):
        self.variant.stock_quantity = 5
        self.variant.save(update_fields=['stock_quantity'])

        with self.captureOnCommitCallbacks(execute=True):
            StockService.manual_adjustment(self.variant, 1, user=self.manager, comment='Inventory count')

        notifications = self.assert_staff_notified(Notification.EventType.LOW_STOCK)
        self.assertTrue(notifications.filter(message__contains='Текущий остаток: 1').exists())

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
        self.assertTrue(notifications.filter(message__contains='Создан:').exists())

    def test_import_completed_with_errors_creates_notification(self):
        import_job = ImportJob.objects.create(
            file=SimpleUploadedFile(
                'partial-products.csv',
                (
                    'product_name,category_slug,price,sku,stock_quantity\n'
                    'Valid Import Product,staff-shoes,100.00,VALID-PARTIAL-SKU,5\n'
                    'Invalid Import Product,missing-category,100.00,INVALID-PARTIAL-SKU,5\n'
                ).encode('utf-8'),
                content_type='text/csv',
            ),
            created_by=self.manager,
            status=ImportJob.Status.PENDING,
        )

        process_product_import.apply(args=(import_job.pk,), throw=True)

        import_job.refresh_from_db()
        self.assertEqual(import_job.status, ImportJob.Status.COMPLETED_WITH_ERRORS)
        notifications = self.assert_staff_notified(Notification.EventType.IMPORT_ERROR)
        self.assertTrue(notifications.filter(message__contains='1 строк завершились с ошибками').exists())

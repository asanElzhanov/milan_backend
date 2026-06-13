from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, Review
from apps.notifications.services import EmailNotificationService
from apps.notifications.tasks import (
    send_order_cancelled_email,
    send_order_created_email,
    send_order_paid_email,
    send_order_status_changed_email,
    send_review_published_email,
    send_review_rejected_email,
)
from apps.orders.models import Order, OrderItem


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='noreply@example.com',
)
class EmailNotificationTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='customer@example.com')
        self.category = Category.objects.create(name='Shoes', slug='email-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='email-nike')
        self.product = Product.objects.create(
            sku='SKU-EMAIL',
            name='Email Product',
            slug='email-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-EMAIL',
            stock_quantity=5,
        )

    def create_order(self, **overrides):
        data = {
            'user': self.user,
            'customer_name': 'Customer Name',
            'phone': '+77011234567',
            'email': 'customer@example.com',
            'city': 'Almaty',
            'delivery_address': 'Abay 10',
            'delivery_method': Order.DeliveryMethod.COURIER,
            'items_total': Decimal('200.00'),
            'delivery_price': Decimal('0.00'),
            'total_amount': Decimal('200.00'),
            'status': Order.Status.NEW,
            'payment_status': Order.PaymentStatus.UNPAID,
        }
        data.update(overrides)
        return Order.objects.create(**data)

    def create_review(self, **overrides):
        order = self.create_order(status=Order.Status.COMPLETED)
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
        data = {
            'product': self.product,
            'user': self.user,
            'order': order,
            'rating': 5,
            'text': 'Great',
            'status': Review.Status.PENDING,
        }
        data.update(overrides)
        return Review.objects.create(**data)

    def test_send_order_created_email_sends_key_order_data(self):
        order = self.create_order()

        send_order_created_email.apply(args=(order.pk,), throw=True)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn(order.order_number, email.subject)
        self.assertIn(order.order_number, email.body)
        self.assertIn('200.00', email.body)
        self.assertIn('Customer Name', email.body)
        self.assertIn(order.get_status_display(), email.body)

    def test_order_email_tasks_send_messages(self):
        order = self.create_order(
            status=Order.Status.PAID,
            payment_status=Order.PaymentStatus.PAID,
        )

        send_order_paid_email.apply(args=(order.pk,), throw=True)
        send_order_status_changed_email.apply(
            args=(order.pk, Order.Status.NEW, Order.Status.PROCESSING),
            throw=True,
        )
        send_order_cancelled_email.apply(args=(order.pk,), throw=True)

        self.assertEqual(len(mail.outbox), 3)
        bodies = '\n'.join(email.body for email in mail.outbox)
        self.assertIn(order.order_number, bodies)
        self.assertIn(order.get_payment_status_display(), bodies)
        self.assertIn(str(dict(Order.Status.choices)[Order.Status.NEW]), bodies)
        self.assertIn(str(dict(Order.Status.choices)[Order.Status.PROCESSING]), bodies)

    def test_review_email_tasks_send_messages(self):
        published_review = self.create_review(
            status=Review.Status.PUBLISHED,
            moderation_comment='Thank you',
        )
        rejected_review = self.create_review(
            order=self.create_order(status=Order.Status.COMPLETED),
            status=Review.Status.REJECTED,
            moderation_comment='Please edit text',
        )

        send_review_published_email.apply(args=(published_review.pk,), throw=True)
        send_review_rejected_email.apply(args=(rejected_review.pk,), throw=True)

        self.assertEqual(len(mail.outbox), 2)
        bodies = '\n'.join(email.body for email in mail.outbox)
        self.assertIn(self.product.name, bodies)
        self.assertIn('опубликован', bodies)
        self.assertIn('отклонён', bodies)
        self.assertIn('Thank you', bodies)
        self.assertIn('Please edit text', bodies)

    def test_missing_order_exits_safely(self):
        send_order_created_email.apply(args=(999999,), throw=True)

        self.assertEqual(mail.outbox, [])

    def test_missing_review_exits_safely(self):
        send_review_published_email.apply(args=(999999,), throw=True)

        self.assertEqual(mail.outbox, [])

    def test_missing_email_does_not_crash_or_send(self):
        order = self.create_order(email='')

        send_order_created_email.apply(args=(order.pk,), throw=True)

        self.assertEqual(mail.outbox, [])

    def test_order_created_email_is_scheduled_on_commit(self):
        order = self.create_order()

        with patch('apps.notifications.tasks.send_order_created_email.delay') as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                EmailNotificationService.schedule_order_created_email(order)
                delay.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()

        delay.assert_called_once_with(order.pk)

from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.services import ProductReviewService, ReviewModerationService
from apps.orders.models import Order
from apps.orders.services import CartService, CheckoutService, OrderStatusService
from apps.recommendations.constants import EventSource, EventType
from apps.recommendations.models import UserProductEvent
from apps.recommendations.services import RecommendationEventService

from .factories import (
    add_order_item,
    make_cart,
    make_delivery_method,
    make_order,
    make_product,
    make_user,
)


class BusinessIntegrationTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(stock=50)

    def test_wishlist_add_and_remove_events_preserve_api_contract(self):
        client = APIClient()
        client.force_authenticate(self.user)
        url = f'/api/v1/auth/wishlist/toggle/{self.product.id}/'
        added = client.post(url)
        removed = client.post(url)
        self.assertEqual((added.status_code, added.data), (201, {'status': 'added'}))
        self.assertEqual((removed.status_code, removed.data), (200, {'status': 'removed'}))
        self.assertEqual(
            list(UserProductEvent.objects.order_by('id').values_list('event_type', flat=True)),
            [EventType.FAVORITE_ADD, EventType.FAVORITE_REMOVE],
        )

    def test_cart_delta_remove_and_clear_events(self):
        cart = make_cart(self.user)
        variant = self.product.variants.get()
        item, _ = CartService.add_item(cart, variant, 2)
        item, _ = CartService.update_item(cart, item, 4)
        item, _ = CartService.update_item(cart, item, 1)
        CartService.remove_item(cart, item)

        second = make_product(stock=20)
        third = make_product(stock=20)
        CartService.add_item(cart, second.variants.get(), 1)
        CartService.add_item(cart, third.variants.get(), 2)
        CartService.clear_cart(cart)
        events = list(UserProductEvent.objects.filter(source=EventSource.CART).order_by('id'))
        self.assertEqual([event.event_type for event in events[:4]], [
            EventType.CART_ADD, EventType.CART_ADD, EventType.CART_REMOVE, EventType.CART_REMOVE,
        ])
        self.assertEqual([float(event.value) for event in events[:4]], [2, 2, -3, -1])
        self.assertEqual(
            UserProductEvent.objects.filter(source=EventSource.CART, event_type=EventType.CART_REMOVE).count(),
            4,
        )

    def test_checkout_paid_webhook_idempotency_cancel_and_return(self):
        delivery = make_delivery_method()
        cart = make_cart(self.user)
        CartService.add_item(cart, self.product.variants.get(), 2)
        order = CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Buyer',
            phone='+77000000000',
            email='buyer@example.com',
            delivery_address='Test street, 1',
            delivery_method=delivery.code,
        )
        self.assertEqual(UserProductEvent.objects.filter(event_type=EventType.ORDER_CREATED).count(), 1)
        OrderStatusService.mark_paid(order)
        OrderStatusService.mark_paid(order)
        self.assertEqual(UserProductEvent.objects.filter(event_type=EventType.PURCHASE).count(), 1)
        OrderStatusService.cancel_order(order)
        self.assertEqual(UserProductEvent.objects.filter(event_type=EventType.ORDER_CANCEL).count(), 1)

        returned_order = make_order(
            user=self.user,
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
        )
        add_order_item(returned_order, self.product)
        OrderStatusService.change_status(returned_order, Order.Status.RETURNED)
        self.assertEqual(UserProductEvent.objects.filter(event_type=EventType.RETURN).count(), 1)

    def test_cancel_before_payment_does_not_create_purchase(self):
        order = make_order(user=self.user)
        add_order_item(order, self.product)
        OrderStatusService.cancel_order(order)
        self.assertFalse(UserProductEvent.objects.filter(event_type=EventType.PURCHASE).exists())
        self.assertTrue(UserProductEvent.objects.filter(event_type=EventType.ORDER_CANCEL).exists())

    def test_review_event_only_when_review_is_published(self):
        order = make_order(
            user=self.user,
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
        )
        add_order_item(order, self.product)
        review = ProductReviewService.create_review(
            user=self.user, product=self.product, order=order, rating=5, text='Excellent',
        )
        self.assertFalse(UserProductEvent.objects.filter(event_type=EventType.RATING).exists())
        manager = make_user(role='manager')
        ReviewModerationService.publish_review(review, manager)
        ReviewModerationService.publish_review(review, manager)
        event = UserProductEvent.objects.get(event_type=EventType.RATING)
        self.assertEqual(int(event.value), 5)

    def test_rollback_removes_event_and_task_is_enqueued_after_commit(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                RecommendationEventService.record_business_event(
                    event_type=EventType.CART_ADD,
                    source=EventSource.CART,
                    user=self.user,
                    product=self.product,
                    value=1,
                )
                raise RuntimeError('rollback')
        self.assertFalse(UserProductEvent.objects.exists())

        with patch('apps.recommendations.tasks.refresh_user_recommendations.delay') as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                RecommendationEventService.record_business_event(
                    event_type=EventType.CART_ADD,
                    source=EventSource.CART,
                    user=self.user,
                    product=self.product,
                    value=1,
                )
            delay.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
            delay.assert_called_once_with(self.user.id)

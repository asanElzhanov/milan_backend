from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.orders.models import Order
from apps.payments.models import Payment


class PaymentCreatePermissionTests(APITestCase):
    stripe_url = '/api/v1/payments/stripe/create-intent/'
    kaspi_url = '/api/v1/payments/kaspi/create/'

    def create_order(self, *, user=None, email='customer@example.com'):
        return Order.objects.create(
            user=user,
            customer_name='Customer',
            phone='+77011234567',
            email=email,
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('100.00'),
            status=Order.Status.NEW,
            payment_status=Order.PaymentStatus.UNPAID,
        )

    @patch('apps.payments.views.stripe.PaymentIntent.create')
    def test_user_can_create_stripe_payment_for_own_order(self, create_intent):
        user = User.objects.create_user(email='owner@example.com')
        order = self.create_order(user=user, email=user.email)
        create_intent.return_value = SimpleNamespace(id='pi_own', client_secret='secret_own')
        self.client.force_authenticate(user=user)

        response = self.client.post(
            self.stripe_url,
            {'order_number': order.order_number},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['client_secret'], 'secret_own')
        self.assertTrue(
            Payment.objects.filter(
                order=order,
                provider=Payment.Provider.STRIPE,
                provider_payment_id='pi_own',
            ).exists()
        )

    @patch('apps.payments.views.stripe.PaymentIntent.create')
    def test_user_cannot_create_stripe_payment_for_other_users_order(self, create_intent):
        owner = User.objects.create_user(email='payment-owner@example.com')
        other = User.objects.create_user(email='payment-other@example.com')
        order = self.create_order(user=owner, email=owner.email)
        self.client.force_authenticate(user=other)

        response = self.client.post(
            self.stripe_url,
            {'order_number': order.order_number},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        create_intent.assert_not_called()
        self.assertFalse(Payment.objects.filter(order=order).exists())

    @patch('apps.payments.views.stripe.PaymentIntent.create')
    def test_guest_can_create_stripe_payment_for_guest_order_with_matching_email(self, create_intent):
        order = self.create_order(user=None, email='guest@example.com')
        create_intent.return_value = SimpleNamespace(id='pi_guest', client_secret='secret_guest')

        response = self.client.post(
            self.stripe_url,
            {'order_number': order.order_number, 'email': 'guest@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['client_secret'], 'secret_guest')

    @patch('apps.payments.views.stripe.PaymentIntent.create')
    def test_guest_cannot_create_stripe_payment_for_guest_order_with_wrong_email(self, create_intent):
        order = self.create_order(user=None, email='guest@example.com')

        response = self.client.post(
            self.stripe_url,
            {'order_number': order.order_number, 'email': 'other@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        create_intent.assert_not_called()
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_user_cannot_create_kaspi_payment_for_other_users_order(self):
        owner = User.objects.create_user(email='kaspi-owner@example.com')
        other = User.objects.create_user(email='kaspi-other@example.com')
        order = self.create_order(user=owner, email=owner.email)
        self.client.force_authenticate(user=other)

        response = self.client.post(
            self.kaspi_url,
            {'order_number': order.order_number},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Payment.objects.filter(order=order).exists())

from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.orders.models import Order
from apps.payments.models import Payment


class FreedomCreatePermissionTests(APITestCase):
    create_url = '/api/v1/payments/freedom/create/'
    status_url = '/api/v1/payments/freedom/status/'

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

    @patch('apps.payments.views.freedompay.init_payment')
    def test_user_can_create_payment_for_own_order(self, init_payment):
        user = User.objects.create_user(email='owner@example.com')
        order = self.create_order(user=user, email=user.email)
        init_payment.return_value = ('ok', 'pay_own', 'https://api.freedompay.kz/pay/pay_own', {})
        self.client.force_authenticate(user=user)

        response = self.client.post(
            self.create_url,
            {'order_number': order.order_number},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['redirect_url'], 'https://api.freedompay.kz/pay/pay_own')
        self.assertTrue(
            Payment.objects.filter(
                order=order,
                provider=Payment.Provider.FREEDOM,
                provider_payment_id='pay_own',
            ).exists()
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.WAITING_PAYMENT)

    @patch('apps.payments.views.freedompay.init_payment')
    def test_user_cannot_create_payment_for_other_users_order(self, init_payment):
        owner = User.objects.create_user(email='payment-owner@example.com')
        other = User.objects.create_user(email='payment-other@example.com')
        order = self.create_order(user=owner, email=owner.email)
        self.client.force_authenticate(user=other)

        response = self.client.post(
            self.create_url,
            {'order_number': order.order_number},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        init_payment.assert_not_called()
        self.assertFalse(Payment.objects.filter(order=order).exists())

    @patch('apps.payments.views.freedompay.init_payment')
    def test_guest_can_create_payment_with_matching_email(self, init_payment):
        order = self.create_order(user=None, email='guest@example.com')
        init_payment.return_value = ('ok', 'pay_guest', 'https://api.freedompay.kz/pay/pay_guest', {})

        response = self.client.post(
            self.create_url,
            {'order_number': order.order_number, 'email': 'guest@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['redirect_url'], 'https://api.freedompay.kz/pay/pay_guest')

    @patch('apps.payments.views.freedompay.init_payment')
    def test_guest_cannot_create_payment_with_wrong_email(self, init_payment):
        order = self.create_order(user=None, email='guest@example.com')

        response = self.client.post(
            self.create_url,
            {'order_number': order.order_number, 'email': 'other@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        init_payment.assert_not_called()
        self.assertFalse(Payment.objects.filter(order=order).exists())

    @patch('apps.payments.views.freedompay.init_payment')
    def test_rejected_init_returns_400(self, init_payment):
        order = self.create_order(user=None, email='guest@example.com')
        init_payment.return_value = ('error', '', '', {'pg_error_description': 'bad merchant'})

        response = self.client.post(
            self.create_url,
            {'order_number': order.order_number, 'email': 'guest@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_status_response_contains_three_language_labels(self):
        order = self.create_order(user=None, email='status-guest@example.com')

        response = self.client.get(self.status_url, {
            'order_number': order.order_number,
            'email': order.email,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Order.Status.NEW)
        self.assertEqual(response.data['status_labels']['kz'], 'Жаңа')
        self.assertEqual(response.data['payment_status'], Order.PaymentStatus.UNPAID)
        self.assertEqual(response.data['payment_status_labels']['en'], 'Unpaid')

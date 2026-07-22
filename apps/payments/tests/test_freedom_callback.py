import xml.etree.ElementTree as ET
from decimal import Decimal

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.orders.models import Order
from apps.payments import freedompay
from apps.payments.models import Payment


TEST_SECRET = 'test_secret_key'


@override_settings(FREEDOMPAY_SECRET_KEY=TEST_SECRET)
class FreedomResultCallbackTests(APITestCase):
    result_url = '/api/v1/payments/freedom/result'

    def setUp(self):
        self.order = Order.objects.create(
            customer_name='Customer',
            phone='+77011234567',
            email='guest@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('100.00'),
            status=Order.Status.WAITING_PAYMENT,
            payment_status=Order.PaymentStatus.WAITING,
        )
        self.payment = Payment.objects.create(
            order=self.order,
            provider=Payment.Provider.FREEDOM,
            amount=Decimal('100.00'),
            provider_payment_id='pay_1',
            status=Payment.Status.PENDING,
        )

    def _signed(self, params):
        params = dict(params)
        params.setdefault('pg_salt', 'salt123')
        params['pg_sig'] = freedompay.generate_signature(
            freedompay.RESULT_SCRIPT, params, TEST_SECRET
        )
        return params

    def _parse_status(self, response):
        return ET.fromstring(response.content.decode()).findtext('pg_status')

    def test_successful_payment_marks_order_paid(self):
        params = self._signed(
            {
                'pg_order_id': self.order.order_number,
                'pg_payment_id': 'pay_1',
                'pg_result': '1',
                'pg_amount': '100.00',
            }
        )

        response = self.client.post(self.result_url, params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._parse_status(response), 'ok')
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.PAID)
        self.assertEqual(self.payment.status, Payment.Status.SUCCESS)

    def test_invalid_signature_is_rejected(self):
        params = {
            'pg_order_id': self.order.order_number,
            'pg_result': '1',
            'pg_salt': 'salt123',
            'pg_sig': 'deadbeef',
        }

        response = self.client.post(self.result_url, params)

        self.assertEqual(self._parse_status(response), 'rejected')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.WAITING)

    def test_failed_payment_marks_payment_failed(self):
        params = self._signed(
            {
                'pg_order_id': self.order.order_number,
                'pg_payment_id': 'pay_1',
                'pg_result': '0',
                'pg_failure_description': 'insufficient funds',
            }
        )

        response = self.client.post(self.result_url, params)

        self.assertEqual(self._parse_status(response), 'ok')
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_repeated_success_callback_is_idempotent(self):
        params = self._signed(
            {
                'pg_order_id': self.order.order_number,
                'pg_payment_id': 'pay_1',
                'pg_result': '1',
            }
        )

        first = self.client.post(self.result_url, params)
        second = self.client.post(self.result_url, params)

        self.assertEqual(self._parse_status(first), 'ok')
        self.assertEqual(self._parse_status(second), 'ok')
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)


@override_settings(FREEDOMPAY_SECRET_KEY=TEST_SECRET)
class FreedomSignatureTests(APITestCase):
    def test_signature_matches_documented_example(self):
        # init_payment.php;25;test;<merchant>;23;molbulak;<secret>
        params = {
            'pg_amount': '25',
            'pg_description': 'test',
            'pg_merchant_id': '<merchant>',
            'pg_order_id': '23',
            'pg_salt': 'molbulak',
        }
        expected_parts = 'init_payment.php;25;test;<merchant>;23;molbulak;<secret>'
        import hashlib

        expected = hashlib.md5(expected_parts.encode()).hexdigest()
        actual = freedompay.generate_signature('init_payment.php', params, '<secret>')
        self.assertEqual(actual, expected)

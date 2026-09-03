from rest_framework import status
from rest_framework.test import APISimpleTestCase

from apps.catalog.models import ImportJob, Review
from apps.orders.models import Order
from apps.payments.models import Payment


class SystemStatusesApiTests(APISimpleTestCase):
    def test_registry_contains_every_system_status_with_three_languages(self):
        response = self.client.get('/api/v1/statuses/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_values = {
            'order': set(Order.Status.values),
            'order_payment': set(Order.PaymentStatus.values),
            'payment': set(Payment.Status.values),
            'import_job': set(ImportJob.Status.values),
            'review': set(Review.Status.values),
            'notification': {'read', 'unread'},
        }
        self.assertEqual(set(response.data), set(expected_values))
        for group, values in expected_values.items():
            options = response.data[group]
            self.assertEqual({option['value'] for option in options}, values)
            for option in options:
                self.assertEqual(set(option['labels']), {'ru', 'kz', 'en'})
                self.assertTrue(all(option['labels'].values()))

    def test_registry_is_public(self):
        response = self.client.get('/api/v1/statuses/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

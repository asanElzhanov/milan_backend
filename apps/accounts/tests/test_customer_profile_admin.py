from decimal import Decimal

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from apps.accounts.admin import CustomerProfileAdmin
from apps.accounts.models import CustomerProfile, User
from apps.orders.models import Order


class CustomerProfileAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='crm-admin@example.com',
            password='secret123',
        )
        self.customer = User.objects.create_user(
            email='crm-customer@example.com',
            phone='+77015550101',
            first_name='CRM',
            last_name='Customer',
        )
        self.client.force_login(self.admin_user)
        self.profile = self.customer.customer_profile

    def create_order(self, *, status, payment_status, total_amount, city='Almaty'):
        return Order.objects.create(
            user=self.customer,
            customer_name='CRM Customer',
            phone='+77015550101',
            email=self.customer.email,
            city=city,
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal(total_amount),
            status=status,
            payment_status=payment_status,
        )

    def test_customer_profile_is_created_for_customer_user(self):
        self.assertTrue(CustomerProfile.objects.filter(user=self.customer).exists())
        self.assertEqual(self.profile.source, CustomerProfile.Source.WEBSITE)

    def test_customer_profile_admin_shows_order_statistics(self):
        self.create_order(
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
            total_amount='100.00',
        )
        self.create_order(
            status=Order.Status.NEW,
            payment_status=Order.PaymentStatus.PAID,
            total_amount='150.00',
        )
        self.create_order(
            status=Order.Status.NEW,
            payment_status=Order.PaymentStatus.UNPAID,
            total_amount='999.00',
        )

        response = self.client.get(reverse('admin:accounts_customerprofile_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'crm-customer@example.com')
        self.assertContains(response, '3')
        self.assertContains(response, '250.00')
        self.assertContains(response, 'Открыть заказы')

    def test_customer_profile_admin_saves_source_and_manager_comment(self):
        response = self.client.post(
            reverse('admin:accounts_customerprofile_change', args=[self.profile.pk]),
            {
                'user': self.customer.pk,
                'source': CustomerProfile.Source.INSTAGRAM,
                'manager_comment': 'Prefers evening calls',
                '_save': 'Save',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.source, CustomerProfile.Source.INSTAGRAM)
        self.assertEqual(self.profile.manager_comment, 'Prefers evening calls')

    def test_customer_profile_admin_searches_by_customer_data(self):
        response = self.client.get(
            reverse('admin:accounts_customerprofile_changelist'),
            {'q': '+77015550101'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'crm-customer@example.com')

    def test_customer_profile_admin_filters_are_configured(self):
        model_admin = CustomerProfileAdmin(CustomerProfile, admin.site)

        self.assertEqual(model_admin.list_filter, ('source', 'created_at'))

    def test_customer_profile_queryset_uses_annotations_and_select_related(self):
        self.create_order(
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
            total_amount='100.00',
        )
        model_admin = CustomerProfileAdmin(CustomerProfile, admin.site)

        with self.assertNumQueries(1):
            profiles = list(model_admin.get_queryset(request=None))
            rows = [
                (
                    profile.user.email,
                    profile._orders_count,
                    profile._total_orders_amount,
                    profile._last_order,
                )
                for profile in profiles
            ]

        self.assertIn(
            ('crm-customer@example.com', 1, Decimal('100.00'), profiles[0]._last_order),
            rows,
        )

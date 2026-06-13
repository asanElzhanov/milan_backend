from decimal import Decimal

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.admin import ReviewAdmin
from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, Review
from apps.orders.models import Order, OrderItem


class ReviewAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='review-admin@example.com',
            password='secret123',
        )
        self.client.force_login(self.admin_user)
        self.api_client = APIClient()
        self.customer = User.objects.create_user(email='review-customer@example.com')
        self.manager = User.objects.create_user(
            email='review-manager-admin@example.com',
            password='secret123',
            role=User.Role.MANAGER,
            is_staff=True,
        )
        self.category = Category.objects.create(name='Shoes', slug='review-admin-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='review-admin-nike')
        self.product = Product.objects.create(
            sku='SKU-REVIEW-ADMIN',
            name='Review Admin Product',
            slug='review-admin-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-REVIEW-ADMIN',
            stock_quantity=5,
        )
        self.order = Order.objects.create(
            user=self.customer,
            customer_name='Review Customer',
            phone='+77011234567',
            email=self.customer.email,
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('100.00'),
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
        )
        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            product_name=self.product.name,
            product_slug=self.product.slug,
            sku=self.variant.sku,
            unit_price=Decimal('100.00'),
            quantity=1,
            total_price=Decimal('100.00'),
        )

    def create_review(self, rating=5, status=Review.Status.PENDING, text='Admin moderation'):
        return Review.objects.create(
            product=self.product,
            user=self.customer,
            order=self.order,
            rating=rating,
            text=text,
            status=status,
        )

    def public_reviews(self):
        response = self.api_client.get(f'/api/v1/catalog/products/{self.product.slug}/reviews/')
        if isinstance(response.data, dict) and 'results' in response.data:
            return response.data['results']
        return response.data

    def test_review_admin_list_is_configured_for_moderation(self):
        model_admin = ReviewAdmin(Review, admin.site)

        self.assertEqual(
            model_admin.list_display,
            (
                'id', 'product_link', 'user_link', 'order_link', 'rating', 'status', 'short_text',
                'created_at', 'moderated_by', 'moderated_at',
            ),
        )
        self.assertEqual(model_admin.list_filter, ('status', 'rating', 'created_at', 'moderated_at'))
        self.assertEqual(model_admin.ordering, ('-created_at',))
        self.assertIn('status', model_admin.list_filter)

    def test_review_admin_short_text_truncates_long_text(self):
        review = self.create_review(text='x' * 130)
        model_admin = ReviewAdmin(Review, admin.site)

        self.assertEqual(model_admin.short_text(review), f'{"x" * 100}...')

    def test_review_admin_publish_action_uses_moderation_service(self):
        review = self.create_review()

        response = self.client.post(
            reverse('admin:catalog_review_changelist'),
            {
                'action': 'publish_reviews',
                '_selected_action': [review.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PUBLISHED)
        self.assertEqual(review.moderated_by, self.admin_user)
        self.assertIsNotNone(review.moderated_at)
        self.assertEqual(self.product.rating, Decimal('5.00'))
        self.assertEqual(self.product.reviews_count, 1)
        self.assertEqual(len(self.public_reviews()), 1)

    def test_review_admin_reject_action_uses_moderation_service(self):
        review = self.create_review(rating=2)

        response = self.client.post(
            reverse('admin:catalog_review_changelist'),
            {
                'action': 'reject_reviews',
                '_selected_action': [review.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertEqual(review.moderated_by, self.admin_user)
        self.assertIsNotNone(review.moderated_at)
        self.assertEqual(self.product.reviews_count, 0)
        self.assertEqual(len(self.public_reviews()), 0)

    def test_review_admin_hide_action_uses_moderation_service(self):
        review = self.create_review()
        self.client.post(
            reverse('admin:catalog_review_changelist'),
            {
                'action': 'publish_reviews',
                '_selected_action': [review.pk],
            },
        )
        self.assertEqual(len(self.public_reviews()), 1)

        response = self.client.post(
            reverse('admin:catalog_review_changelist'),
            {
                'action': 'hide_reviews',
                '_selected_action': [review.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(review.status, Review.Status.HIDDEN)
        self.assertEqual(review.moderated_by, self.admin_user)
        self.assertIsNotNone(review.moderated_at)
        self.assertEqual(self.product.reviews_count, 0)
        self.assertEqual(len(self.public_reviews()), 0)

    def test_review_admin_status_change_uses_moderation_service(self):
        review = self.create_review()

        response = self.client.post(
            reverse('admin:catalog_review_change', args=[review.pk]),
            {
                'status': Review.Status.PUBLISHED,
                'moderation_comment': 'Looks good',
                '_save': 'Save',
            },
        )

        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PUBLISHED)
        self.assertEqual(review.moderated_by, self.admin_user)
        self.assertEqual(review.moderation_comment, 'Looks good')
        self.assertEqual(self.product.reviews_count, 1)

    def test_manager_can_access_review_admin_and_moderate_with_audit(self):
        self.client.force_login(self.manager)
        review = self.create_review()

        response = self.client.post(
            reverse('admin:catalog_review_changelist'),
            {
                'action': 'publish_reviews',
                '_selected_action': [review.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PUBLISHED)
        self.assertEqual(review.moderated_by, self.manager)
        self.assertIsNotNone(review.moderated_at)
        self.assertEqual(self.product.reviews_count, 1)

    def test_normal_user_cannot_access_review_admin(self):
        self.client.force_login(self.customer)
        review = self.create_review()

        response = self.client.get(reverse('admin:catalog_review_change', args=[review.pk]))

        self.assertNotEqual(response.status_code, 200)

    def test_review_admin_rejects_unsupported_pending_status_change(self):
        review = self.create_review(status=Review.Status.PUBLISHED)

        response = self.client.post(
            reverse('admin:catalog_review_change', args=[review.pk]),
            {
                'status': Review.Status.PENDING,
                'moderation_comment': '',
                '_save': 'Save',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Этот статус нельзя установить из админки.')
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PUBLISHED)

    def test_review_admin_disallows_add(self):
        response = self.client.get(reverse('admin:catalog_review_add'))

        self.assertEqual(response.status_code, 403)

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

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
        self.customer = User.objects.create_user(email='review-customer@example.com')
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

    def create_review(self, rating=5, status=Review.Status.PENDING):
        return Review.objects.create(
            product=self.product,
            user=self.customer,
            order=self.order,
            rating=rating,
            text='Admin moderation',
            status=status,
        )

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

    def test_review_admin_disallows_add(self):
        response = self.client.get(reverse('admin:catalog_review_add'))

        self.assertEqual(response.status_code, 403)

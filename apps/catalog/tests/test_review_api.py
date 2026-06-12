from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, Review
from apps.catalog.services import ReviewModerationService
from apps.orders.models import Order, OrderItem


class ReviewApiTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shoes', slug='api-review-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='api-review-nike')
        self.user = User.objects.create_user(
            email='api-review@example.com',
            first_name='Aida',
        )
        self.other_user = User.objects.create_user(email='other-api-review@example.com')
        self.manager = User.objects.create_user(
            email='api-review-manager@example.com',
            role=User.Role.MANAGER,
        )
        self.product = Product.objects.create(
            sku='SKU-API-REVIEW',
            name='API Review Product',
            slug='api-review-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.other_product = Product.objects.create(
            sku='SKU-API-OTHER-REVIEW',
            name='API Other Review Product',
            slug='api-other-review-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('150.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-API-REVIEW',
            stock_quantity=5,
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.other_product,
            sku='VAR-API-OTHER-REVIEW',
            stock_quantity=5,
        )

    def create_order(self, *, user=None, status_value=Order.Status.COMPLETED):
        user = user or self.user
        return Order.objects.create(
            user=user,
            customer_name='Review Customer',
            phone='+77011234567',
            email=user.email,
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('200.00'),
            status=status_value,
            payment_status=Order.PaymentStatus.PAID,
        )

    def add_item(self, order, variant=None):
        variant = variant or self.variant
        return OrderItem.objects.create(
            order=order,
            variant=variant,
            product_name=variant.product.name,
            product_slug=variant.product.slug,
            sku=variant.sku,
            unit_price=Decimal('100.00'),
            quantity=1,
            total_price=Decimal('100.00'),
        )

    def create_url(self):
        return '/api/v1/catalog/reviews/'

    def list_url(self, product=None):
        product = product or self.product
        return f'/api/v1/catalog/products/{product.slug}/reviews/'

    def detail_url(self, product=None):
        product = product or self.product
        return f'/api/v1/catalog/products/{product.slug}/'

    def response_results(self, response):
        if isinstance(response.data, dict) and 'results' in response.data:
            return response.data['results']
        return response.data

    def test_authenticated_user_can_create_review_after_purchase(self):
        order = self.create_order()
        self.add_item(order)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.create_url(), {
            'product_slug': self.product.slug,
            'order_number': order.order_number,
            'rating': 5,
            'text': 'Excellent',
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['product'], self.product.id)
        self.assertEqual(response.data['order'], order.id)
        self.assertEqual(response.data['rating'], 5)
        self.assertEqual(response.data['text'], 'Excellent')
        self.assertEqual(response.data['status'], Review.Status.PENDING)
        review = Review.objects.get()
        self.assertEqual(review.product, self.product)
        self.assertEqual(review.order, order)
        self.assertTrue(review.is_verified_purchase)

    def test_anonymous_user_cannot_create_review(self):
        order = self.create_order()
        self.add_item(order)

        response = self.client.post(self.create_url(), {
            'product_id': self.product.id,
            'order_id': order.id,
            'rating': 5,
            'text': 'Anonymous',
        })

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Review.objects.exists())

    def test_cannot_create_review_without_purchase(self):
        order = self.create_order()
        self.add_item(order, self.other_variant)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.create_url(), {
            'product_id': self.product.id,
            'order_id': order.id,
            'rating': 5,
            'text': 'No purchase',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Review.objects.exists())

    def test_cannot_create_duplicate_review(self):
        order = self.create_order()
        self.add_item(order)
        Review.objects.create(
            product=self.product,
            user=self.user,
            order=order,
            rating=5,
            text='Existing',
            status=Review.Status.PENDING,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.create_url(), {
            'product_id': self.product.id,
            'order_id': order.id,
            'rating': 4,
            'text': 'Duplicate',
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Review.objects.count(), 1)

    def test_product_review_list_returns_only_published_reviews(self):
        order = self.create_order()
        other_order = self.create_order(user=self.other_user)
        self.add_item(order)
        self.add_item(other_order)
        Review.objects.create(
            product=self.product,
            user=self.user,
            order=order,
            rating=5,
            text='Published',
            status=Review.Status.PUBLISHED,
        )
        Review.objects.create(
            product=self.product,
            user=self.other_user,
            order=other_order,
            rating=4,
            text='Pending',
            status=Review.Status.PENDING,
        )
        Review.objects.create(
            product=self.product,
            user=self.other_user,
            order=self.create_order(user=self.other_user),
            rating=3,
            text='Rejected',
            status=Review.Status.REJECTED,
        )
        Review.objects.create(
            product=self.product,
            user=self.other_user,
            order=self.create_order(user=self.other_user),
            rating=2,
            text='Hidden',
            status=Review.Status.HIDDEN,
        )

        response = self.client.get(self.list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.response_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['text'], 'Published')
        self.assertEqual(results[0]['user_name'], 'Aida')
        self.assertNotIn('status', results[0])

    def test_product_review_list_is_public(self):
        order = self.create_order()
        self.add_item(order)
        Review.objects.create(
            product=self.product,
            user=self.user,
            order=order,
            rating=5,
            text='Public',
            status=Review.Status.PUBLISHED,
        )

        response = self.client.get(self.list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.response_results(response)), 1)

    def test_published_review_appears_publicly_and_updates_rating(self):
        order = self.create_order()
        self.add_item(order)
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(self.create_url(), {
            'product_id': self.product.id,
            'order_id': order.id,
            'rating': 5,
            'text': 'Needs moderation',
        })
        review = Review.objects.get(pk=create_response.data['id'])

        pending_list_response = self.client.get(self.list_url())
        ReviewModerationService.publish_review(review, self.manager)
        published_list_response = self.client.get(self.list_url())
        detail_response = self.client.get(self.detail_url())

        self.assertEqual(len(self.response_results(pending_list_response)), 0)
        self.assertEqual(len(self.response_results(published_list_response)), 1)
        self.assertEqual(self.response_results(published_list_response)[0]['text'], 'Needs moderation')
        self.assertEqual(detail_response.data['average_rating'], 5.0)
        self.assertEqual(detail_response.data['reviews_count'], 1)

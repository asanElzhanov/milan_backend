from decimal import Decimal
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, Review
from apps.catalog.services import ProductReviewService, ReviewModerationService
from apps.orders.models import Order, OrderItem


class ReviewApiTests(APITestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory(dir=settings.BASE_DIR)
        self.addCleanup(self.media_directory.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.category = Category.objects.create(name_ru='Shoes', slug='api-review-shoes')
        self.brand = Brand.objects.create(name_ru='Nike', slug='api-review-nike')
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
            name_ru='API Review Product',
            slug='api-review-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.other_product = Product.objects.create(
            sku='SKU-API-OTHER-REVIEW',
            name_ru='API Other Review Product',
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
            product_name=variant.product.name_ru,
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
        self.assertEqual(response.data['product']['id'], self.product.id)
        self.assertEqual(response.data['order']['id'], order.id)
        self.assertEqual(response.data['user_name'], 'Aida')
        self.assertEqual(response.data['rating'], 5)
        self.assertEqual(response.data['text'], 'Excellent')
        self.assertEqual(response.data['status'], Review.Status.PENDING)
        self.assertEqual(response.data['media'], [])
        self.assertTrue(response.data['is_verified_purchase'])
        review = Review.objects.get()
        self.assertEqual(review.product, self.product)
        self.assertEqual(review.order, order)
        self.assertTrue(review.is_verified_purchase)

    def test_create_review_accepts_images_and_videos(self):
        order = self.create_order()
        self.add_item(order)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.create_url(), {
            'product_slug': self.product.slug,
            'order_number': order.order_number,
            'rating': 5,
            'text': 'Review with media',
            'media': [
                SimpleUploadedFile('photo.jpg', b'image content', content_type='image/jpeg'),
                SimpleUploadedFile('clip.mp4', b'video content', content_type='video/mp4'),
            ],
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['media']), 2)
        self.assertEqual(
            {item['media_type'] for item in response.data['media']},
            {'image', 'video'},
        )
        review = Review.objects.get(pk=response.data['id'])
        self.assertEqual(review.images.count(), 2)

    def test_create_review_rejects_too_many_media_files(self):
        order = self.create_order()
        self.add_item(order)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.create_url(), {
            'product_id': self.product.id,
            'order_id': order.id,
            'rating': 5,
            'media': [
                SimpleUploadedFile(f'{index}.jpg', b'image', content_type='image/jpeg')
                for index in range(6)
            ],
        }, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('media', response.data)
        self.assertFalse(Review.objects.exists())

    def test_my_reviews_returns_only_authenticated_users_reviews(self):
        order = self.create_order()
        self.add_item(order)
        own_review = Review.objects.create(
            product=self.product,
            user=self.user,
            order=order,
            rating=5,
            text='Mine',
            status=Review.Status.PENDING,
            is_verified_purchase=True,
        )
        other_order = self.create_order(user=self.other_user)
        self.add_item(other_order)
        Review.objects.create(
            product=self.product,
            user=self.other_user,
            order=other_order,
            rating=3,
            text='Not mine',
            status=Review.Status.PUBLISHED,
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.get('/api/v1/catalog/reviews/mine/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.response_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], own_review.id)
        self.assertEqual(results[0]['status'], Review.Status.PENDING)
        self.assertEqual(results[0]['product']['id'], self.product.id)
        self.assertEqual(results[0]['order']['id'], order.id)

    def test_my_reviews_requires_authentication(self):
        response = self.client.get('/api/v1/catalog/reviews/mine/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_review_api_uses_review_service(self):
        order = self.create_order()
        self.add_item(order)
        self.client.force_authenticate(user=self.user)

        with patch.object(
            ProductReviewService,
            'create_review',
            wraps=ProductReviewService.create_review,
        ) as create_review:
            response = self.client.post(self.create_url(), {
                'product_id': self.product.id,
                'order_id': order.id,
                'rating': 5,
                'text': 'Created through service',
            })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        create_review.assert_called_once()

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

from decimal import Decimal
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import (
    Brand, Category, Color, Product, ProductImage,
    ProductMedia, ProductVariant, Review, Size,
)
from apps.orders.models import Order


class ProductDetailApiTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.category = Category.objects.create(name='Shoes', slug='shoes')
        self.brand = Brand.objects.create(name='Nike', slug='nike')
        self.black = Color.objects.create(name='Black', slug='black', hex_code='#000000')
        self.white = Color.objects.create(name='White', slug='white', hex_code='#FFFFFF')
        self.size_41 = Size.objects.create(value='41', size_type=Size.SizeType.SHOES, sort_order=1)
        self.size_42 = Size.objects.create(value='42', size_type=Size.SizeType.SHOES, sort_order=2)
        self.product = Product.objects.create(
            sku='SKU-DETAIL',
            name='Air Max',
            slug='air-max',
            category=self.category,
            brand=self.brand,
            description='Running shoes',
            price=Decimal('100.00'),
            old_price=Decimal('120.00'),
            seo_title='Air Max SEO',
            seo_description='Air Max SEO description',
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def detail_url(self, product=None):
        product = product or self.product
        return f'/api/v1/catalog/products/{product.slug}/'

    def similar_url(self, product=None):
        product = product or self.product
        return f'/api/v1/catalog/products/{product.slug}/similar/'

    def make_image_file(self, name='product.jpg'):
        return SimpleUploadedFile(name, b'image content', content_type='image/jpeg')

    def make_order(self, user, suffix):
        return Order.objects.create(
            user=user,
            customer_name=f'Customer {suffix}',
            phone='+77011234567',
            email=user.email,
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('100.00'),
            status=Order.Status.COMPLETED,
            payment_status=Order.PaymentStatus.PAID,
        )

    def test_get_product_by_slug(self):
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.product.id)
        self.assertEqual(response.data['slug'], self.product.slug)
        self.assertEqual(response.data['description'], 'Running shoes')
        self.assertEqual(response.data['category']['slug'], self.category.slug)
        self.assertEqual(response.data['brand']['slug'], self.brand.slug)
        self.assertEqual(response.data['seo_title'], 'Air Max SEO')
        self.assertEqual(response.data['seo_description'], 'Air Max SEO description')

    def test_similar_products_do_not_use_inactive_source_product(self):
        self.product.is_active = False
        self.product.save(update_fields=['is_active', 'updated_at'])

        response = self.client.get(self.similar_url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_product_is_not_public(self):
        inactive = Product.objects.create(
            sku='SKU-INACTIVE-DETAIL',
            name='Inactive',
            slug='inactive-detail',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
            is_active=False,
        )

        response = self.client.get(self.detail_url(inactive))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_returns_sorted_images(self):
        ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('second.jpg'),
            sort_order=2,
        )
        ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('first.jpg'),
            is_main=True,
            sort_order=1,
            alt_text='Front view',
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['images']), 2)
        self.assertIn('first', response.data['images'][0]['image'])
        self.assertTrue(response.data['images'][0]['is_main'])
        self.assertEqual(response.data['images'][0]['alt_text'], 'Front view')

    def test_detail_returns_media(self):
        ProductMedia.objects.create(
            product=self.product,
            media_type=ProductMedia.MediaType.VIDEO,
            url='https://example.com/video.mp4',
            title='Runway video',
        )
        ProductMedia.objects.create(
            product=self.product,
            media_type=ProductMedia.MediaType.VIDEO,
            url='https://example.com/inactive.mp4',
            is_active=False,
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['media']), 1)
        self.assertEqual(response.data['media'][0]['url'], 'https://example.com/video.mp4')

    def test_detail_returns_variants_with_stock_and_effective_price(self):
        ProductVariant.objects.create(
            product=self.product,
            color=self.black,
            size=self.size_41,
            sku='VAR-DETAIL-1',
            stock_quantity=3,
        )
        ProductVariant.objects.create(
            product=self.product,
            color=self.white,
            size=self.size_42,
            sku='VAR-DETAIL-2',
            stock_quantity=0,
            variant_price=Decimal('90.00'),
            is_active=False,
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['variants']), 2)
        first_variant = response.data['variants'][0]
        second_variant = response.data['variants'][1]
        self.assertEqual(first_variant['sku'], 'VAR-DETAIL-1')
        self.assertEqual(first_variant['stock_quantity'], 3)
        self.assertEqual(Decimal(first_variant['effective_price']), Decimal('100.00'))
        self.assertTrue(first_variant['active'])
        self.assertTrue(first_variant['in_stock'])
        self.assertEqual(Decimal(second_variant['effective_price']), Decimal('90.00'))
        self.assertFalse(second_variant['active'])
        self.assertFalse(second_variant['in_stock'])

    def test_available_sizes_and_colors_are_calculated_from_active_variants(self):
        ProductVariant.objects.create(
            product=self.product,
            color=self.black,
            size=self.size_41,
            sku='VAR-ACTIVE-1',
            stock_quantity=0,
        )
        ProductVariant.objects.create(
            product=self.product,
            color=self.white,
            size=self.size_42,
            sku='VAR-INACTIVE-1',
            stock_quantity=5,
            is_active=False,
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([size['value'] for size in response.data['available_sizes']], ['41'])
        self.assertEqual([color['slug'] for color in response.data['available_colors']], ['black'])

    def test_average_rating_and_reviews_use_approved_reviews(self):
        first_user = User.objects.create_user(email='first@example.com')
        second_user = User.objects.create_user(email='second@example.com')
        third_user = User.objects.create_user(email='third@example.com')
        Review.objects.create(
            product=self.product,
            user=first_user,
            order=self.make_order(first_user, 'First'),
            rating=5,
            text='Great',
            status=Review.Status.PUBLISHED,
        )
        Review.objects.create(
            product=self.product,
            user=second_user,
            order=self.make_order(second_user, 'Second'),
            rating=3,
            text='Good',
            status=Review.Status.PUBLISHED,
        )
        Review.objects.create(
            product=self.product,
            user=third_user,
            order=self.make_order(third_user, 'Third'),
            rating=1,
            text='Hidden',
            status=Review.Status.HIDDEN,
        )
        pending_user = User.objects.create_user(email='pending@example.com')
        rejected_user = User.objects.create_user(email='rejected@example.com')
        Review.objects.create(
            product=self.product,
            user=pending_user,
            order=self.make_order(pending_user, 'Pending'),
            rating=1,
            text='Pending',
            status=Review.Status.PENDING,
        )
        Review.objects.create(
            product=self.product,
            user=rejected_user,
            order=self.make_order(rejected_user, 'Rejected'),
            rating=1,
            text='Rejected',
            status=Review.Status.REJECTED,
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['average_rating'], 4.0)
        self.assertEqual(response.data['reviews_count'], 2)
        self.assertEqual(len(response.data['reviews']), 2)
        self.assertEqual(
            {review['text'] for review in response.data['reviews']},
            {'Great', 'Good'},
        )

    def test_rating_values_are_empty_without_published_reviews(self):
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['average_rating'])
        self.assertEqual(response.data['reviews_count'], 0)
        self.assertEqual(response.data['reviews'], [])

    def test_product_detail_uses_bounded_number_of_queries(self):
        ProductImage.objects.create(
            product=self.product,
            image=self.make_image_file('detail-main.jpg'),
            is_main=True,
        )
        ProductMedia.objects.create(
            product=self.product,
            media_type=ProductMedia.MediaType.IMAGE,
            file=self.make_image_file('detail-media.jpg'),
        )
        ProductVariant.objects.create(
            product=self.product,
            color=self.black,
            size=self.size_41,
            sku='VAR-PERF-DETAIL-1',
            stock_quantity=3,
        )
        ProductVariant.objects.create(
            product=self.product,
            color=self.white,
            size=self.size_42,
            sku='VAR-PERF-DETAIL-2',
            stock_quantity=0,
            variant_price=Decimal('90.00'),
        )
        first_user = User.objects.create_user(email='perf-first@example.com')
        second_user = User.objects.create_user(email='perf-second@example.com')
        Review.objects.create(
            product=self.product,
            user=first_user,
            order=self.make_order(first_user, 'Perf First'),
            rating=5,
            text='Great',
            status=Review.Status.PUBLISHED,
        )
        Review.objects.create(
            product=self.product,
            user=second_user,
            order=self.make_order(second_user, 'Perf Second'),
            rating=4,
            text='Good',
            status=Review.Status.PUBLISHED,
        )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['images']), 1)
        self.assertEqual(len(response.data['media']), 1)
        self.assertEqual(len(response.data['variants']), 2)
        self.assertEqual(len(response.data['reviews']), 2)
        self.assertLessEqual(len(captured), 10)

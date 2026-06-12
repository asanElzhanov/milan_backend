from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, Review
from apps.catalog.services import (
    DuplicateReviewError,
    InvalidReviewRatingError,
    ProductReviewService,
    ReviewModerationError,
    ReviewModerationService,
    ReviewNotAllowedError,
)
from apps.orders.models import Order, OrderItem


DEFAULT_USER = object()


class ProductReviewServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shoes', slug='review-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='review-nike')
        self.user = User.objects.create_user(email='review@example.com')
        self.other_user = User.objects.create_user(email='other-review@example.com')
        self.manager = User.objects.create_user(
            email='review-manager@example.com',
            role=User.Role.MANAGER,
        )
        self.admin = User.objects.create_user(
            email='review-admin@example.com',
            role=User.Role.ADMIN,
        )
        self.product = self.create_product('SKU-REVIEW-1', 'Review Product', 'review-product')
        self.other_product = self.create_product(
            'SKU-REVIEW-2',
            'Other Review Product',
            'other-review-product',
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-REVIEW-1',
            stock_quantity=5,
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.other_product,
            sku='VAR-REVIEW-2',
            stock_quantity=5,
        )

    def create_product(self, sku, name, slug):
        return Product.objects.create(
            sku=sku,
            name=name,
            slug=slug,
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )

    def create_order(self, *, user=DEFAULT_USER, status=Order.Status.COMPLETED):
        user = self.user if user is DEFAULT_USER else user
        return Order.objects.create(
            user=user,
            customer_name='Review Customer',
            phone='+77011234567',
            email=user.email if user else 'guest@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            total_amount=Decimal('200.00'),
            status=status,
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

    def test_user_can_create_review_after_purchase(self):
        order = self.create_order()
        self.add_item(order)

        review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=order,
            rating=5,
            text='Great shoes',
        )

        self.assertEqual(review.user, self.user)
        self.assertEqual(review.product, self.product)
        self.assertEqual(review.order, order)
        self.assertEqual(review.status, Review.Status.PENDING)
        self.assertTrue(review.is_verified_purchase)

    def test_cannot_create_review_without_purchase(self):
        order = self.create_order()
        self.add_item(order, self.other_variant)

        with self.assertRaises(ReviewNotAllowedError):
            ProductReviewService.create_review(
                user=self.user,
                product=self.product,
                order=order,
                rating=5,
                text='No purchase',
            )

    def test_cannot_create_review_for_other_users_order(self):
        order = self.create_order(user=self.other_user)
        self.add_item(order)

        with self.assertRaises(ReviewNotAllowedError):
            ProductReviewService.create_review(
                user=self.user,
                product=self.product,
                order=order,
                rating=5,
                text='Wrong owner',
            )

    def test_cannot_create_review_for_unfinished_order(self):
        order = self.create_order(status=Order.Status.NEW)
        self.add_item(order)

        with self.assertRaises(ReviewNotAllowedError):
            ProductReviewService.create_review(
                user=self.user,
                product=self.product,
                order=order,
                rating=5,
                text='Too early',
            )

    def test_cannot_create_duplicate_review_for_same_product_in_same_order(self):
        order = self.create_order()
        self.add_item(order)
        ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=order,
            rating=5,
            text='First',
        )

        with self.assertRaises(DuplicateReviewError):
            ProductReviewService.create_review(
                user=self.user,
                product=self.product,
                order=order,
                rating=4,
                text='Second',
            )

    def test_can_create_reviews_for_different_products_in_same_order(self):
        order = self.create_order()
        self.add_item(order, self.variant)
        self.add_item(order, self.other_variant)

        first_review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=order,
            rating=5,
            text='First product',
        )
        second_review = ProductReviewService.create_review(
            user=self.user,
            product=self.other_product,
            order=order,
            rating=4,
            text='Second product',
        )

        self.assertEqual(first_review.status, Review.Status.PENDING)
        self.assertEqual(second_review.status, Review.Status.PENDING)
        self.assertEqual(Review.objects.count(), 2)

    def test_can_create_review_for_same_product_in_another_order(self):
        first_order = self.create_order()
        second_order = self.create_order()
        self.add_item(first_order)
        self.add_item(second_order)
        ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=first_order,
            rating=5,
            text='First order',
        )

        review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=second_order,
            rating=4,
            text='Second order',
        )

        self.assertEqual(review.order, second_order)
        self.assertEqual(Review.objects.count(), 2)

    def test_paid_order_is_allowed(self):
        order = self.create_order(status=Order.Status.PAID)
        self.add_item(order)

        self.assertTrue(ProductReviewService.can_review_product(self.user, self.product, order))

    def test_guest_order_is_not_allowed_from_account(self):
        order = self.create_order(user=None)
        self.add_item(order)

        with self.assertRaises(ReviewNotAllowedError):
            ProductReviewService.create_review(
                user=self.user,
                product=self.product,
                order=order,
                rating=5,
                text='Guest order',
            )

    def test_invalid_rating_is_rejected(self):
        order = self.create_order()
        self.add_item(order)

        with self.assertRaises(InvalidReviewRatingError):
            ProductReviewService.create_review(
                user=self.user,
                product=self.product,
                order=order,
                rating=6,
                text='Bad rating',
            )

    def test_manager_can_publish_review_and_update_rating(self):
        order = self.create_order()
        self.add_item(order)
        review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=order,
            rating=5,
            text='Pending',
        )

        moderated_review = ReviewModerationService.publish_review(
            review,
            self.manager,
            comment='Looks good',
        )

        self.product.refresh_from_db()
        self.assertEqual(moderated_review.status, Review.Status.PUBLISHED)
        self.assertEqual(moderated_review.moderated_by, self.manager)
        self.assertIsNotNone(moderated_review.moderated_at)
        self.assertEqual(moderated_review.moderation_comment, 'Looks good')
        self.assertEqual(self.product.rating, Decimal('5.00'))
        self.assertEqual(self.product.reviews_count, 1)

    def test_admin_can_reject_review(self):
        order = self.create_order()
        self.add_item(order)
        review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=order,
            rating=2,
            text='Pending',
        )

        moderated_review = ReviewModerationService.reject_review(review, self.admin)

        self.product.refresh_from_db()
        self.assertEqual(moderated_review.status, Review.Status.REJECTED)
        self.assertEqual(moderated_review.moderated_by, self.admin)
        self.assertEqual(self.product.rating, Decimal('0.00'))
        self.assertEqual(self.product.reviews_count, 0)

    def test_hiding_published_review_recalculates_rating(self):
        first_order = self.create_order()
        second_order = self.create_order()
        self.add_item(first_order)
        self.add_item(second_order)
        first_review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=first_order,
            rating=5,
            text='First',
        )
        second_review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=second_order,
            rating=3,
            text='Second',
        )
        ReviewModerationService.publish_review(first_review, self.manager)
        ReviewModerationService.publish_review(second_review, self.manager)

        ReviewModerationService.hide_review(first_review, self.manager)

        self.product.refresh_from_db()
        first_review.refresh_from_db()
        self.assertEqual(first_review.status, Review.Status.HIDDEN)
        self.assertEqual(self.product.rating, Decimal('3.00'))
        self.assertEqual(self.product.reviews_count, 1)

    def test_regular_user_cannot_moderate_review(self):
        order = self.create_order()
        self.add_item(order)
        review = ProductReviewService.create_review(
            user=self.user,
            product=self.product,
            order=order,
            rating=5,
            text='Pending',
        )

        with self.assertRaises(ReviewModerationError):
            ReviewModerationService.publish_review(review, self.user)

        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PENDING)

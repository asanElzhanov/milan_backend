from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import PromoCode
from apps.orders.services import CartService


class CartPromoApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Promo API Shoes', slug='promo-api-shoes')
        brand = Brand.objects.create(name_ru='Promo API Brand', slug='promo-api-brand')
        self.product = Product.objects.create(
            sku='SKU-CART-PROMO-API',
            name_ru='Cart Promo API Product',
            slug='cart-promo-api-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-CART-PROMO-API',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.user = User.objects.create_user(email='cart-promo-api@example.com')

    def cart_url(self):
        return '/api/v1/orders/cart/'

    def items_url(self):
        return '/api/v1/orders/cart/items/'

    def apply_url(self):
        return '/api/v1/orders/cart/promo-code/apply/'

    def promo_url(self):
        return '/api/v1/orders/cart/promo-code/'

    def auth_headers(self, token):
        return {'HTTP_X_CART_TOKEN': token}

    def create_promo_code(self, **overrides):
        data = {
            'code': 'PROMO10',
            'discount_type': PromoCode.DiscountType.PERCENT,
            'value': Decimal('10.00'),
        }
        data.update(overrides)
        return PromoCode.objects.create(**data)

    def create_guest_cart(self, quantity=2):
        response = self.client.post(
            self.items_url(),
            {'variant_id': self.variant.id, 'quantity': quantity},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data['cart_token']

    def create_user_cart(self, quantity=2):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.items_url(),
            {'variant_id': self.variant.id, 'quantity': quantity},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_guest_applies_promo_code(self):
        promo_code = self.create_promo_code()
        token = self.create_guest_cart()

        response = self.client.post(
            self.apply_url(),
            {'code': ' promo10 '},
            format='json',
            **self.auth_headers(token),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cart_token'], token)
        self.assertEqual(response.data['subtotal'], '240.00')
        self.assertEqual(response.data['promo_code'], 'PROMO10')
        self.assertEqual(response.data['discount_amount'], '24.00')
        self.assertEqual(response.data['total_after_discount'], '216.00')
        self.assertEqual(response.data['total'], '216.00')
        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 0)

    def test_user_applies_promo_code(self):
        self.create_promo_code(
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('50.00'),
        )
        self.create_user_cart()

        response = self.client.post(self.apply_url(), {'code': 'PROMO10'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['cart_token'])
        self.assertEqual(response.data['promo_code'], 'PROMO10')
        self.assertEqual(response.data['discount_amount'], '50.00')
        self.assertEqual(response.data['total_after_discount'], '190.00')

    def test_inactive_promo_code_is_rejected(self):
        self.create_promo_code(is_active=False)
        token = self.create_guest_cart()

        response = self.client.post(
            self.apply_url(),
            {'code': 'PROMO10'},
            format='json',
            **self.auth_headers(token),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

    def test_expired_promo_code_is_rejected(self):
        self.create_promo_code(valid_until=timezone.now() - timedelta(days=1))
        token = self.create_guest_cart()

        response = self.client.post(
            self.apply_url(),
            {'code': 'PROMO10'},
            format='json',
            **self.auth_headers(token),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

    def test_min_order_amount_is_checked(self):
        self.create_promo_code(min_order_amount=Decimal('300.00'))
        token = self.create_guest_cart()

        response = self.client.post(
            self.apply_url(),
            {'code': 'PROMO10'},
            format='json',
            **self.auth_headers(token),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

    def test_get_cart_shows_applied_promo_code_discount(self):
        self.create_promo_code()
        token = self.create_guest_cart()
        self.client.post(
            self.apply_url(),
            {'code': 'PROMO10'},
            format='json',
            **self.auth_headers(token),
        )

        response = self.client.get(self.cart_url(), **self.auth_headers(token))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['promo_code'], 'PROMO10')
        self.assertEqual(response.data['discount_amount'], '24.00')
        self.assertEqual(response.data['total'], '216.00')

    def test_delete_promo_code_recalculates_cart(self):
        self.create_promo_code()
        token = self.create_guest_cart()
        self.client.post(
            self.apply_url(),
            {'code': 'PROMO10'},
            format='json',
            **self.auth_headers(token),
        )

        response = self.client.delete(self.promo_url(), **self.auth_headers(token))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['promo_code'])
        self.assertEqual(response.data['discount_amount'], '0.00')
        self.assertEqual(response.data['total_after_discount'], '240.00')
        self.assertEqual(response.data['total'], '240.00')

    def test_apply_promo_code_to_empty_cart_is_rejected(self):
        self.create_promo_code()
        cart = CartService.get_or_create_user_cart(self.user)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.apply_url(), {'code': 'PROMO10'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        cart.refresh_from_db()
        self.assertIsNone(cart.promo_code)

    def test_apply_promo_code_does_not_increment_used_count(self):
        promo_code = self.create_promo_code()
        token = self.create_guest_cart()

        self.client.post(
            self.apply_url(),
            {'code': 'PROMO10'},
            format='json',
            **self.auth_headers(token),
        )

        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 0)

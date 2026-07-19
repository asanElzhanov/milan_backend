from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import CartItem
from apps.orders.services import CartService


class UserCartApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='user-cart-shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='user-cart-nike')
        self.product = Product.objects.create(
            sku='SKU-USER-CART',
            name_ru='User Cart Product',
            slug='user-cart-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-USER-CART',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-USER-CART-OTHER',
            stock_quantity=4,
        )
        self.user = User.objects.create_user(email='cart-user@example.com')
        self.other_user = User.objects.create_user(email='other-cart-user@example.com')
        self.client.force_authenticate(user=self.user)

    def cart_url(self):
        return '/api/v1/orders/cart/'

    def items_url(self):
        return '/api/v1/orders/cart/items/'

    def item_url(self, item_id):
        return f'/api/v1/orders/cart/items/{item_id}/'

    def clear_url(self):
        return '/api/v1/orders/cart/clear/'

    def add_item(self, variant=None, quantity=1):
        variant = variant or self.variant
        response = self.client.post(
            self.items_url(),
            {'variant_id': variant.id, 'quantity': quantity},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def test_user_gets_own_cart_without_token(self):
        response = self.client.get(self.cart_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['cart_token'])
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['items_count'], 0)

        cart = CartService.get_or_create_user_cart(self.user)
        self.assertEqual(cart.user, self.user)
        self.assertTrue(cart.is_active)

    def test_user_adds_item(self):
        response = self.add_item(quantity=2)

        self.assertIsNone(response.data['cart_token'])
        self.assertEqual(response.data['items_count'], 1)
        self.assertEqual(response.data['total_quantity'], 2)
        self.assertEqual(response.data['subtotal'], '240.00')
        self.assertEqual(response.data['items'][0]['variant_id'], self.variant.id)

        cart = CartService.get_or_create_user_cart(self.user)
        self.assertEqual(cart.items.get(variant=self.variant).quantity, 2)

    def test_user_add_duplicate_variant_increases_quantity(self):
        self.add_item(quantity=1)

        response = self.add_item(quantity=2)

        self.assertEqual(response.data['items_count'], 1)
        self.assertEqual(response.data['total_quantity'], 3)
        self.assertEqual(response.data['items'][0]['quantity'], 3)

    def test_user_updates_quantity(self):
        response = self.add_item(quantity=1)
        item_id = response.data['items'][0]['id']

        response = self.client.patch(
            self.item_url(item_id),
            {'quantity': 4},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'][0]['quantity'], 4)
        self.assertEqual(response.data['total_quantity'], 4)
        self.assertEqual(response.data['subtotal'], '480.00')

    def test_user_deletes_item(self):
        response = self.add_item(quantity=1)
        item_id = response.data['items'][0]['id']

        response = self.client.delete(self.item_url(item_id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['items_count'], 0)

    def test_user_clears_cart(self):
        self.add_item(quantity=1)
        self.add_item(variant=self.other_variant, quantity=2)

        response = self.client.delete(self.clear_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['total_quantity'], 0)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_user_cannot_change_item_from_another_user_cart(self):
        other_cart = CartService.get_or_create_user_cart(self.other_user)
        other_item, _ = CartService.add_item(other_cart, self.other_variant, 1)

        response = self.client.patch(
            self.item_url(other_item.id),
            {'quantity': 2},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        other_item.refresh_from_db()
        self.assertEqual(other_item.quantity, 1)

    def test_user_cannot_delete_item_from_another_user_cart(self):
        other_cart = CartService.get_or_create_user_cart(self.other_user)
        other_item, _ = CartService.add_item(other_cart, self.other_variant, 1)

        response = self.client.delete(self.item_url(other_item.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CartItem.objects.filter(pk=other_item.pk, cart=other_cart).exists())

    def test_user_cart_recalculates_sum_after_changes(self):
        self.add_item(quantity=1)
        response = self.add_item(variant=self.other_variant, quantity=2)

        self.assertEqual(response.data['items_count'], 2)
        self.assertEqual(response.data['total_quantity'], 3)
        self.assertEqual(response.data['subtotal'], '320.00')
        self.assertEqual(response.data['total'], '320.00')

    def test_user_cart_checks_stock(self):
        response = self.client.post(
            self.items_url(),
            {'variant_id': self.variant.id, 'quantity': 6},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)

    def test_user_cart_ignores_guest_token_and_does_not_merge(self):
        self.client.force_authenticate(user=None)
        guest_response = self.client.post(
            self.items_url(),
            {'variant_id': self.variant.id, 'quantity': 1},
            format='json',
        )
        guest_token = guest_response.data['cart_token']

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.items_url(),
            {'variant_id': self.other_variant.id, 'quantity': 1},
            format='json',
            HTTP_X_CART_TOKEN=guest_token,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items_count'], 1)
        self.assertEqual(response.data['items'][0]['variant_id'], self.other_variant.id)
        guest_cart = CartService.get_or_create_guest_cart(guest_token)
        self.assertEqual(guest_cart.items.get(variant=self.variant).quantity, 1)

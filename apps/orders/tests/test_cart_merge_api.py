from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.models import CartItem
from apps.orders.services import CartService


class CartMergeApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name_ru='Shoes', slug='merge-cart-shoes')
        brand = Brand.objects.create(name_ru='Nike', slug='merge-cart-nike')
        self.product = Product.objects.create(
            sku='SKU-MERGE-CART',
            name_ru='Merge Cart Product',
            slug='merge-cart-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-MERGE-CART',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-MERGE-CART-OTHER',
            stock_quantity=4,
        )
        self.user = User.objects.create_user(email='merge-cart@example.com')

    def merge_url(self):
        return '/api/v1/orders/cart/merge/'

    def post_merge(self, token):
        return self.client.post(
            self.merge_url(),
            {'guest_cart_token': str(token)},
            format='json',
        )

    def test_merge_moves_guest_items_to_user_cart(self):
        guest_cart = CartService.get_or_create_guest_cart()
        CartService.add_item(guest_cart, self.variant, 2)
        self.client.force_authenticate(user=self.user)

        response = self.post_merge(guest_cart.token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['cart_token'])
        self.assertEqual(response.data['items_count'], 1)
        self.assertEqual(response.data['total_quantity'], 2)
        self.assertEqual(response.data['subtotal'], '240.00')
        self.assertEqual(response.data['items'][0]['variant_id'], self.variant.id)

        user_cart = CartService.get_or_create_user_cart(self.user)
        self.assertEqual(user_cart.items.get(variant=self.variant).quantity, 2)
        guest_cart.refresh_from_db()
        self.assertFalse(guest_cart.is_active)
        self.assertFalse(guest_cart.items.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_merge_combines_duplicate_variants(self):
        guest_cart = CartService.get_or_create_guest_cart()
        user_cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(guest_cart, self.variant, 2)
        CartService.add_item(user_cart, self.variant, 1)
        self.client.force_authenticate(user=self.user)

        response = self.post_merge(guest_cart.token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items_count'], 1)
        self.assertEqual(response.data['total_quantity'], 3)
        self.assertEqual(response.data['items'][0]['quantity'], 3)
        self.assertEqual(CartItem.objects.filter(cart=user_cart, variant=self.variant).count(), 1)

    def test_merge_checks_stock_and_does_not_partially_merge(self):
        guest_cart = CartService.get_or_create_guest_cart()
        user_cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(guest_cart, self.variant, 2)
        CartService.add_item(guest_cart, self.other_variant, 1)
        CartService.add_item(user_cart, self.variant, 4)
        self.client.force_authenticate(user=self.user)

        response = self.post_merge(guest_cart.token)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

        guest_cart.refresh_from_db()
        user_cart.refresh_from_db()
        self.assertTrue(guest_cart.is_active)
        self.assertEqual(guest_cart.items.get(variant=self.variant).quantity, 2)
        self.assertEqual(guest_cart.items.get(variant=self.other_variant).quantity, 1)
        self.assertEqual(user_cart.items.get(variant=self.variant).quantity, 4)
        self.assertFalse(user_cart.items.filter(variant=self.other_variant).exists())

    def test_merge_deactivates_and_clears_guest_cart_after_success(self):
        guest_cart = CartService.get_or_create_guest_cart()
        CartService.add_item(guest_cart, self.other_variant, 1)
        self.client.force_authenticate(user=self.user)

        response = self.post_merge(guest_cart.token)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        guest_cart.refresh_from_db()
        self.assertFalse(guest_cart.is_active)
        self.assertEqual(guest_cart.items.count(), 0)

    def test_merge_requires_authentication(self):
        guest_cart = CartService.get_or_create_guest_cart()
        CartService.add_item(guest_cart, self.variant, 1)

        response = self.post_merge(guest_cart.token)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_merge_returns_clear_error_for_unknown_token(self):
        self.client.force_authenticate(user=self.user)

        response = self.post_merge('00000000-0000-0000-0000-000000000000')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

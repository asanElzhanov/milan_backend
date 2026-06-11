from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.models import Cart, CartItem
from apps.orders.services import (
    CartNotFoundError,
    CartService,
    InactiveVariantError,
    InvalidCartQuantityError,
    NotEnoughStockError,
)


class CartServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shoes', slug='cart-shoes')
        self.brand = Brand.objects.create(name='Nike', slug='cart-nike')
        self.product = Product.objects.create(
            sku='SKU-CART-SERVICE',
            name='Cart Service Product',
            slug='cart-service-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-CART-SERVICE',
            stock_quantity=5,
        )
        self.premium_variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-CART-PREMIUM',
            stock_quantity=3,
            variant_price=Decimal('125.00'),
        )
        self.user = User.objects.create_user(email='cart-service@example.com')

    def test_get_or_create_guest_cart_creates_cart_with_token(self):
        cart = CartService.get_or_create_guest_cart()

        self.assertIsNone(cart.user)
        self.assertTrue(cart.is_active)
        self.assertIsNotNone(cart.token)

    def test_get_or_create_guest_cart_returns_active_cart_by_token(self):
        cart = CartService.get_or_create_guest_cart()

        found = CartService.get_or_create_guest_cart(token=str(cart.token))

        self.assertEqual(found, cart)

    def test_get_or_create_guest_cart_raises_for_unknown_token(self):
        with self.assertRaises(CartNotFoundError):
            CartService.get_or_create_guest_cart(token='00000000-0000-0000-0000-000000000000')

    def test_get_or_create_user_cart_returns_single_active_cart(self):
        first = CartService.get_or_create_user_cart(self.user)
        second = CartService.get_or_create_user_cart(self.user)

        self.assertEqual(first, second)
        self.assertEqual(Cart.objects.filter(user=self.user, is_active=True).count(), 1)
        self.assertIsNone(first.token)

    def test_add_item_adds_position(self):
        cart = CartService.get_or_create_guest_cart()

        item, returned_cart = CartService.add_item(cart, self.variant, 2)

        self.assertEqual(returned_cart, cart)
        self.assertEqual(item.variant, self.variant)
        self.assertEqual(item.quantity, 2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertFalse(StockMovement.objects.exists())

    def test_add_item_increases_quantity_for_duplicate_variant(self):
        cart = CartService.get_or_create_guest_cart()
        CartService.add_item(cart, self.variant, 1)

        item, _ = CartService.add_item(cart, self.variant, 2)

        self.assertEqual(item.quantity, 3)
        self.assertEqual(CartItem.objects.filter(cart=cart, variant=self.variant).count(), 1)

    def test_update_item_changes_quantity(self):
        cart = CartService.get_or_create_guest_cart()
        item, _ = CartService.add_item(cart, self.variant, 1)

        updated_item, _ = CartService.update_item(cart, item.pk, 4)

        self.assertEqual(updated_item.pk, item.pk)
        self.assertEqual(updated_item.quantity, 4)

    def test_update_item_rejects_non_positive_quantity(self):
        cart = CartService.get_or_create_guest_cart()
        item, _ = CartService.add_item(cart, self.variant, 1)

        with self.assertRaises(InvalidCartQuantityError):
            CartService.update_item(cart, item.pk, 0)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_remove_item_deletes_position(self):
        cart = CartService.get_or_create_guest_cart()
        CartService.add_item(cart, self.variant, 1)

        CartService.remove_item(cart, self.variant)

        self.assertFalse(CartItem.objects.filter(cart=cart, variant=self.variant).exists())

    def test_clear_cart_deletes_all_positions(self):
        cart = CartService.get_or_create_guest_cart()
        CartService.add_item(cart, self.variant, 1)
        CartService.add_item(cart, self.premium_variant, 1)

        CartService.clear_cart(cart)

        self.assertEqual(cart.items.count(), 0)

    def test_add_item_rejects_quantity_above_stock(self):
        cart = CartService.get_or_create_guest_cart()

        with self.assertRaises(NotEnoughStockError):
            CartService.add_item(cart, self.variant, 6)

        self.assertFalse(CartItem.objects.filter(cart=cart).exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)

    def test_add_item_rejects_inactive_variant(self):
        self.variant.is_active = False
        self.variant.save(update_fields=['is_active'])
        cart = CartService.get_or_create_guest_cart()

        with self.assertRaises(InactiveVariantError):
            CartService.add_item(cart, self.variant, 1)

        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    def test_add_item_rejects_inactive_product(self):
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])
        cart = CartService.get_or_create_guest_cart()

        with self.assertRaises(InactiveVariantError):
            CartService.add_item(cart, self.variant, 1)

        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    def test_recalculate_cart_counts_quantities_and_prices(self):
        cart = CartService.get_or_create_guest_cart()
        CartService.add_item(cart, self.variant, 2)
        CartService.add_item(cart, self.premium_variant, 1)

        totals = CartService.recalculate_cart(cart)

        self.assertEqual(totals['items_count'], 2)
        self.assertEqual(totals['total_quantity'], 3)
        self.assertEqual(totals['subtotal'], Decimal('325.00'))
        self.assertEqual(totals['total'], Decimal('325.00'))

    def test_merge_guest_cart_to_user_cart_moves_items(self):
        guest_cart = CartService.get_or_create_guest_cart()
        CartService.add_item(guest_cart, self.variant, 2)

        user_cart = CartService.merge_guest_cart_to_user_cart(guest_cart.token, self.user)

        item = user_cart.items.get(variant=self.variant)
        self.assertEqual(item.quantity, 2)
        guest_cart.refresh_from_db()
        self.assertFalse(guest_cart.is_active)
        self.assertEqual(guest_cart.items.count(), 0)

    def test_merge_guest_cart_to_user_cart_merges_duplicate_variants(self):
        guest_cart = CartService.get_or_create_guest_cart()
        user_cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(guest_cart, self.variant, 2)
        CartService.add_item(user_cart, self.variant, 1)

        merged_cart = CartService.merge_guest_cart_to_user_cart(guest_cart.token, self.user)

        self.assertEqual(merged_cart.items.get(variant=self.variant).quantity, 3)
        self.assertEqual(merged_cart.items.filter(variant=self.variant).count(), 1)

    def test_merge_guest_cart_to_user_cart_checks_stock_atomically(self):
        guest_cart = CartService.get_or_create_guest_cart()
        user_cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(guest_cart, self.variant, 2)
        CartService.add_item(user_cart, self.variant, 4)

        with self.assertRaises(NotEnoughStockError):
            CartService.merge_guest_cart_to_user_cart(guest_cart.token, self.user)

        user_cart.refresh_from_db()
        guest_cart.refresh_from_db()
        self.assertTrue(guest_cart.is_active)
        self.assertEqual(guest_cart.items.get(variant=self.variant).quantity, 2)
        self.assertEqual(user_cart.items.get(variant=self.variant).quantity, 4)

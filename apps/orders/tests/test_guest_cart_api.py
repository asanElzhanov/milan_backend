from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, Color, Product, ProductImage, ProductVariant, Size
from apps.orders.models import Cart, CartItem
from apps.orders.services import CartService


class GuestCartApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name='Shoes', slug='guest-cart-shoes')
        brand = Brand.objects.create(name='Nike', slug='guest-cart-nike')
        self.color = Color.objects.create(name='Black', slug='guest-cart-black', hex_code='#000000')
        self.size = Size.objects.create(value='42', size_type=Size.SizeType.SHOES, sort_order=1)
        self.product = Product.objects.create(
            sku='SKU-GUEST-CART',
            name='Guest Cart Product',
            slug='guest-cart-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size=self.size,
            sku='VAR-GUEST-CART',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-GUEST-CART-OTHER',
            stock_quantity=4,
        )

    def cart_url(self):
        return '/api/v1/orders/cart/'

    def items_url(self):
        return '/api/v1/orders/cart/items/'

    def item_url(self, item_id):
        return f'/api/v1/orders/cart/items/{item_id}/'

    def clear_url(self):
        return '/api/v1/orders/cart/clear/'

    def auth_headers(self, token):
        return {'HTTP_X_CART_TOKEN': token}

    def create_cart_with_item(self, quantity=1):
        response = self.client.post(
            self.items_url(),
            {'variant_id': self.variant.id, 'quantity': quantity},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data['cart_token']
        item_id = response.data['items'][0]['id']
        return token, item_id, response

    def test_guest_can_create_cart_on_first_add(self):
        token, item_id, response = self.create_cart_with_item(quantity=2)

        self.assertIsNotNone(token)
        self.assertEqual(response.data['items_count'], 1)
        self.assertEqual(response.data['total_quantity'], 2)
        self.assertEqual(response.data['subtotal'], '240.00')
        self.assertEqual(response.data['total'], '240.00')
        item = response.data['items'][0]
        self.assertEqual(item['id'], item_id)
        self.assertEqual(item['variant_id'], self.variant.id)
        self.assertEqual(item['product_id'], self.product.id)
        self.assertEqual(item['product_name'], self.product.name)
        self.assertEqual(item['product_slug'], self.product.slug)
        self.assertEqual(item['sku'], self.variant.sku)
        self.assertEqual(item['size'], self.size.value)
        self.assertEqual(item['color'], self.color.name)
        self.assertEqual(item['unit_price'], '120.00')
        self.assertEqual(item['line_total'], '240.00')
        self.assertEqual(item['available_stock'], 5)
        self.assertTrue(item['in_stock'])

    def test_guest_can_get_cart_by_token(self):
        token, _, _ = self.create_cart_with_item(quantity=1)

        response = self.client.get(self.cart_url(), **self.auth_headers(token))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cart_token'], token)
        self.assertEqual(response.data['items_count'], 1)

    def test_get_cart_requires_token(self):
        response = self.client.get(self.cart_url())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

    def test_guest_can_add_item_to_existing_cart(self):
        token, _, _ = self.create_cart_with_item(quantity=1)

        response = self.client.post(
            self.items_url(),
            {'variant_id': self.other_variant.id, 'quantity': 2},
            format='json',
            **self.auth_headers(token),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cart_token'], token)
        self.assertEqual(response.data['items_count'], 2)
        self.assertEqual(response.data['total_quantity'], 3)
        self.assertEqual(response.data['subtotal'], '320.00')

    def test_guest_can_update_quantity(self):
        token, item_id, _ = self.create_cart_with_item(quantity=1)

        response = self.client.patch(
            self.item_url(item_id),
            {'quantity': 3},
            format='json',
            **self.auth_headers(token),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'][0]['quantity'], 3)
        self.assertEqual(response.data['total_quantity'], 3)
        self.assertEqual(response.data['subtotal'], '360.00')

    def test_guest_can_delete_item(self):
        token, item_id, _ = self.create_cart_with_item(quantity=1)

        response = self.client.delete(self.item_url(item_id), **self.auth_headers(token))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['items_count'], 0)
        self.assertEqual(response.data['total_quantity'], 0)
        self.assertEqual(response.data['subtotal'], '0.00')

    def test_guest_can_clear_cart(self):
        token, _, _ = self.create_cart_with_item(quantity=1)
        self.client.post(
            self.items_url(),
            {'variant_id': self.other_variant.id, 'quantity': 1},
            format='json',
            **self.auth_headers(token),
        )

        response = self.client.delete(self.clear_url(), **self.auth_headers(token))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['items_count'], 0)
        self.assertEqual(response.data['total_quantity'], 0)

    def test_guest_cannot_add_more_than_stock(self):
        response = self.client.post(
            self.items_url(),
            {'variant_id': self.variant.id, 'quantity': 6},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CartItem.objects.exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)

    def test_guest_cannot_delete_item_from_another_cart(self):
        first_token, _, _ = self.create_cart_with_item(quantity=1)
        second_cart = CartService.get_or_create_guest_cart()
        second_item, _ = CartService.add_item(second_cart, self.other_variant, 1)

        response = self.client.delete(
            self.item_url(second_item.id),
            **self.auth_headers(first_token),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(CartItem.objects.filter(pk=second_item.pk, cart=second_cart).exists())

    def test_invalid_token_returns_clear_error(self):
        response = self.client.get(
            self.cart_url(),
            **self.auth_headers('00000000-0000-0000-0000-000000000000'),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

    def test_get_cart_uses_bounded_number_of_queries(self):
        ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile('cart-main.jpg', b'image content', content_type='image/jpeg'),
            is_main=True,
        )
        token, _, _ = self.create_cart_with_item(quantity=1)
        self.client.post(
            self.items_url(),
            {'variant_id': self.other_variant.id, 'quantity': 1},
            format='json',
            **self.auth_headers(token),
        )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.cart_url(), **self.auth_headers(token))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['items']), 2)
        self.assertLessEqual(len(captured), 4)

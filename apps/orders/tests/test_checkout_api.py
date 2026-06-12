from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.models import CartItem, DeliveryMethod, Order, PromoCode
from apps.orders.services import CartService


class CheckoutApiTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name='Shoes', slug='checkout-api-shoes')
        brand = Brand.objects.create(name='Nike', slug='checkout-api-nike')
        self.product = Product.objects.create(
            sku='SKU-CHECKOUT-API',
            name='Checkout API Product',
            slug='checkout-api-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='VAR-CHECKOUT-API',
            stock_quantity=5,
            variant_price=Decimal('120.00'),
        )
        self.user = User.objects.create_user(email='checkout-api@example.com')
        self.courier_delivery = DeliveryMethod.objects.get(code='courier')

    def checkout_url(self):
        return '/api/v1/orders/checkout/'

    def payload(self, **overrides):
        data = {
            'customer_name': 'Customer Name',
            'phone': '+77011234567',
            'email': 'customer@example.com',
            'city': 'Almaty',
            'delivery_address': 'Abay 10',
            'delivery_method': Order.DeliveryMethod.COURIER,
            'comment': 'Leave at reception',
        }
        data.update(overrides)
        return data

    def create_promo_code(self, **overrides):
        data = {
            'code': 'PROMO10',
            'discount_type': PromoCode.DiscountType.PERCENT,
            'value': Decimal('10.00'),
        }
        data.update(overrides)
        return PromoCode.objects.create(**data)

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_user_can_checkout_own_cart(self, _send_email):
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('order_number', response.data)
        self.assertEqual(response.data['customer_name'], 'Customer Name')
        self.assertEqual(response.data['status'], Order.Status.NEW)
        self.assertEqual(response.data['payment_status'], Order.PaymentStatus.UNPAID)
        self.assertEqual(response.data['items_total'], '240.00')
        self.assertEqual(response.data['delivery_price'], '0.00')
        self.assertTrue(response.data['delivery_requires_manager_calculation'])
        self.assertEqual(response.data['total_amount'], '240.00')
        self.assertEqual(response.data['delivery_method'], 'courier')
        self.assertEqual(response.data['delivery_method_code'], 'courier')
        self.assertEqual(len(response.data['items']), 1)
        self.assertEqual(response.data['items'][0]['sku'], self.variant.sku)

        order = Order.objects.get(order_number=response.data['order_number'])
        self.assertEqual(order.user, self.user)
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_checkout_with_fixed_delivery_adds_delivery_price_to_total(self, _send_email):
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['items_total'], '240.00')
        self.assertEqual(response.data['delivery_price'], '1000.00')
        self.assertFalse(response.data['delivery_requires_manager_calculation'])
        self.assertEqual(response.data['total_amount'], '1240.00')

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_checkout_ignores_frontend_delivery_price(self, _send_email):
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(delivery_price='1.00'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['items_total'], '120.00')
        self.assertEqual(response.data['delivery_price'], '1000.00')
        self.assertEqual(response.data['total_amount'], '1120.00')

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_checkout_with_percent_promo_code_saves_discount_snapshot(self, _send_email):
        promo_code = self.create_promo_code()
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)

        response = self.client.post(
            self.checkout_url(),
            self.payload(promo_code='PROMO10'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['items_total'], '240.00')
        self.assertEqual(response.data['promo_code_text'], 'PROMO10')
        self.assertEqual(response.data['discount_amount'], '24.00')
        self.assertEqual(response.data['delivery_price'], '1000.00')
        self.assertEqual(response.data['total_amount'], '1216.00')
        order = Order.objects.get(order_number=response.data['order_number'])
        self.assertEqual(order.promo_code, promo_code)
        self.assertEqual(order.promo_code_text, 'PROMO10')
        self.assertEqual(order.discount_amount, Decimal('24.00'))
        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 1)

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_checkout_uses_promo_code_stored_on_cart(self, _send_email):
        self.create_promo_code(
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('50.00'),
        )
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)
        CartService.apply_promo_code(cart, 'PROMO10', user=self.user)

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['promo_code_text'], 'PROMO10')
        self.assertEqual(response.data['discount_amount'], '50.00')
        self.assertEqual(response.data['total_amount'], '1190.00')
        cart.refresh_from_db()
        self.assertIsNone(cart.promo_code)

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_checkout_ignores_frontend_discount_amount(self, _send_email):
        self.create_promo_code()
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(promo_code='PROMO10', discount_amount='999.00'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['items_total'], '120.00')
        self.assertEqual(response.data['discount_amount'], '12.00')
        self.assertEqual(response.data['total_amount'], '108.00')

    def test_checkout_rejects_expired_promo_code(self):
        promo_code = self.create_promo_code(valid_until=timezone.now() - timedelta(days=1))
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(promo_code='PROMO10'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 0)
        self.assertFalse(Order.objects.exists())

    def test_checkout_checks_usage_limit_at_checkout(self):
        promo_code = self.create_promo_code(usage_limit=1, used_count=1)
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(promo_code='PROMO10'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        promo_code.refresh_from_db()
        self.assertEqual(promo_code.used_count, 1)
        self.assertFalse(Order.objects.exists())

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_checkout_accepts_delivery_method_id(self, _send_email):
        self.courier_delivery.price_type = DeliveryMethod.PriceType.FIXED
        self.courier_delivery.base_price = Decimal('1000.00')
        self.courier_delivery.save(update_fields=['price_type', 'base_price', 'updated_at'])
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(delivery_method='', delivery_method_id=self.courier_delivery.id),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['delivery_method_code'], 'courier')
        self.assertEqual(response.data['delivery_price'], '1000.00')

    def test_checkout_rejects_courier_without_address(self):
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(delivery_address=''),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 5)
        self.assertFalse(StockMovement.objects.exists())

    @patch('apps.orders.views.send_order_confirmation_email.delay')
    def test_guest_can_checkout_by_body_cart_token(self, _send_email):
        cart = CartService.get_or_create_guest_cart()
        CartService.add_item(cart, self.variant, 1)

        response = self.client.post(
            self.checkout_url(),
            self.payload(cart_token=str(cart.token)),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(order_number=response.data['order_number'])
        self.assertIsNone(order.user)
        self.assertEqual(response.data['total_amount'], '120.00')
        self.assertFalse(CartItem.objects.filter(cart=cart).exists())

    def test_guest_without_cart_token_cannot_checkout(self):
        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_empty_cart(self):
        self.client.force_authenticate(user=self.user)
        CartService.get_or_create_user_cart(self.user)

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_not_enough_stock(self):
        self.client.force_authenticate(user=self.user)
        cart = CartService.get_or_create_user_cart(self.user)
        CartService.add_item(cart, self.variant, 2)
        self.variant.stock_quantity = 1
        self.variant.save(update_fields=['stock_quantity'])

        response = self.client.post(self.checkout_url(), self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)
        self.assertFalse(Order.objects.exists())
        self.assertTrue(CartItem.objects.filter(cart=cart).exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 1)

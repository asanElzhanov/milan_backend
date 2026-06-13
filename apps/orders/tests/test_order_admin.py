from decimal import Decimal

from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Brand, Category, Product, ProductVariant, StockMovement
from apps.orders.admin import (
    OrderAdmin, OrderItemInline, OrderStatusHistoryInline,
    PromoCodeAdmin, PromoCodeAdminForm, PromoCodeUsageAdmin,
)
from apps.orders.models import (
    Cart, CartItem, Order, OrderItem, OrderStatusHistory,
    PromoCode, PromoCodeUsage,
)
from apps.orders.services import CheckoutService


class OrderAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='orders-admin@example.com',
            password='secret123',
        )
        self.user = User.objects.create_user(email='order-customer@example.com')
        self.client.force_login(self.admin_user)

        category = Category.objects.create(name='Shoes', slug='order-admin-shoes')
        brand = Brand.objects.create(name='Nike', slug='order-admin-nike')
        product = Product.objects.create(
            sku='SKU-ORDER-ADMIN',
            name='Order Admin Product',
            slug='order-admin-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-ORDER-ADMIN',
            stock_quantity=5,
        )
        cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=2)
        self.order = CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Order Customer',
            phone='+77011234567',
            email='customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
            comment='Admin test',
        )

    def change_url(self):
        return reverse('admin:orders_order_change', args=[self.order.pk])

    def order_post_data(self, status_value=None, item_quantity=None, manager_comment=''):
        item = self.order.items.get()
        history = self.order.status_history.first()
        return {
            'user': self.user.pk,
            'customer_name': self.order.customer_name,
            'phone': self.order.phone,
            'email': self.order.email,
            'city': self.order.city,
            'delivery_address': self.order.delivery_address,
            'delivery_method': self.order.delivery_method,
            'status': status_value or self.order.status,
            'payment_status': self.order.payment_status,
            'comment': self.order.comment,
            'manager_comment': manager_comment,
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '0',
            'items-0-id': item.pk,
            'items-0-order': self.order.pk,
            'items-0-quantity': item_quantity if item_quantity is not None else item.quantity,
            'status_history-TOTAL_FORMS': '1',
            'status_history-INITIAL_FORMS': '1',
            'status_history-MIN_NUM_FORMS': '0',
            'status_history-MAX_NUM_FORMS': '0',
            'status_history-0-id': history.pk,
            'status_history-0-order': self.order.pk,
            '_save': 'Save',
        }

    def test_order_admin_changelist_opens_and_searches_by_item_sku(self):
        response = self.client.get(
            reverse('admin:orders_order_changelist'),
            {'q': 'VAR-ORDER-ADMIN'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)
        self.assertContains(response, 'Order Customer')

    def test_order_admin_searches_by_order_number(self):
        response = self.client.get(
            reverse('admin:orders_order_changelist'),
            {'q': self.order.order_number},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)

    def test_order_admin_searches_by_phone(self):
        response = self.client.get(
            reverse('admin:orders_order_changelist'),
            {'q': '+77011234567'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)

    def test_order_admin_filters_are_configured(self):
        model_admin = OrderAdmin(Order, admin.site)

        self.assertEqual(
            model_admin.list_filter,
            ('status', 'payment_status', 'delivery_method', 'city', 'created_at'),
        )

    def test_order_admin_change_status_uses_service_and_creates_history(self):
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock_quantity, 3)

        response = self.client.post(
            self.change_url(),
            self.order_post_data(
                status_value=Order.Status.CANCELLED,
                manager_comment='Customer called support',
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.CANCELLED)
        self.assertEqual(self.variant.stock_quantity, 5)

        history = OrderStatusHistory.objects.latest('created_at')
        self.assertEqual(history.order, self.order)
        self.assertEqual(history.old_status, Order.Status.NEW)
        self.assertEqual(history.new_status, Order.Status.CANCELLED)
        self.assertEqual(history.changed_by, self.admin_user)
        self.assertEqual(history.comment, 'Customer called support')

        movement = StockMovement.objects.latest('created_at')
        self.assertEqual(movement.operation_type, StockMovement.OperationType.ORDER_CANCEL)
        self.assertEqual(movement.user, self.admin_user)

    def test_order_admin_rejects_invalid_status_transition(self):
        response = self.client.post(
            self.change_url(),
            self.order_post_data(status_value=Order.Status.SHIPPED),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Недопустимый переход статуса new -&gt; shipped')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.NEW)

    def test_order_admin_saves_manager_comment_separately(self):
        response = self.client.post(
            self.change_url(),
            self.order_post_data(manager_comment='Call before delivery'),
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.comment, 'Admin test')
        self.assertEqual(self.order.manager_comment, 'Call before delivery')

    def test_order_item_inline_is_readonly(self):
        response = self.client.post(
            self.change_url(),
            self.order_post_data(item_quantity='99'),
        )

        self.assertEqual(response.status_code, 302)
        item = OrderItem.objects.get(order=self.order)
        self.assertEqual(item.quantity, 2)

    def test_order_item_inline_permissions_are_read_only(self):
        inline = OrderItemInline(Order, admin.site)

        self.assertFalse(inline.has_add_permission(request=None, obj=self.order))
        self.assertFalse(inline.has_change_permission(request=None, obj=self.order))
        self.assertFalse(inline.has_delete_permission(request=None, obj=self.order))
        self.assertEqual(
            inline.readonly_fields,
            (
                'product_name', 'product_slug', 'sku', 'size_name', 'color_name',
                'unit_price', 'quantity', 'total_price',
            ),
        )

    def test_order_status_history_inline_permissions_are_read_only(self):
        inline = OrderStatusHistoryInline(Order, admin.site)

        self.assertFalse(inline.has_add_permission(request=None, obj=self.order))
        self.assertFalse(inline.has_change_permission(request=None, obj=self.order))
        self.assertFalse(inline.has_delete_permission(request=None, obj=self.order))

    def test_order_item_admin_is_read_only(self):
        item = self.order.items.get()

        response = self.client.post(
            reverse('admin:orders_orderitem_change', args=[item.pk]),
            {
                'order': self.order.pk,
                'variant': self.variant.pk,
                'product_name': 'Changed',
                'quantity': 99,
            },
        )

        self.assertEqual(response.status_code, 403)
        item.refresh_from_db()
        self.assertEqual(item.product_name, 'Order Admin Product')
        self.assertEqual(item.quantity, 2)

    def test_order_status_history_admin_is_read_only(self):
        history = self.order.status_history.first()

        response = self.client.post(
            reverse('admin:orders_orderstatushistory_change', args=[history.pk]),
            {
                'old_status': Order.Status.NEW,
                'new_status': Order.Status.PROCESSING,
                'comment': 'Changed',
            },
        )

        self.assertEqual(response.status_code, 403)
        history.refresh_from_db()
        self.assertEqual(history.new_status, Order.Status.NEW)
        self.assertEqual(history.comment, '')

    def test_order_status_history_admin_cannot_delete(self):
        history = self.order.status_history.first()

        response = self.client.post(
            reverse('admin:orders_orderstatushistory_delete', args=[history.pk]),
            {'post': 'yes'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(OrderStatusHistory.objects.filter(pk=history.pk).exists())


class PromoCodeAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='promo-admin@example.com',
            password='secret123',
        )
        self.user = User.objects.create_user(email='promo-admin-customer@example.com')
        self.client.force_login(self.admin_user)

        category = Category.objects.create(name='Promo Admin Shoes', slug='promo-admin-shoes')
        brand = Brand.objects.create(name='Promo Admin Nike', slug='promo-admin-nike')
        product = Product.objects.create(
            sku='SKU-PROMO-ADMIN',
            name='Promo Admin Product',
            slug='promo-admin-product',
            category=category,
            brand=brand,
            price=Decimal('100.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku='VAR-PROMO-ADMIN',
            stock_quantity=5,
        )

    def create_order(self):
        cart = Cart.objects.create(user=self.user, token=None)
        CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        return CheckoutService.checkout(
            cart=cart,
            user=self.user,
            customer_name='Promo Customer',
            phone='+77011234567',
            email='promo-customer@example.com',
            city='Almaty',
            delivery_address='Abay 10',
            delivery_method=Order.DeliveryMethod.COURIER,
        )

    def test_promo_code_admin_changelist_opens_and_searches_by_code(self):
        PromoCode.objects.create(
            code='summer10',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('10.00'),
        )

        response = self.client.get(
            reverse('admin:orders_promocode_changelist'),
            {'q': 'SUMMER10'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SUMMER10')
        self.assertContains(response, 'без лимита')

    def test_promo_code_admin_change_page_opens_with_usage_inline(self):
        promo_code = PromoCode.objects.create(
            code='ORDER10',
            discount_type=PromoCode.DiscountType.PERCENT,
            value=Decimal('10.00'),
        )
        order = self.create_order()
        PromoCodeUsage.objects.create(promo_code=promo_code, order=order, user=self.user)

        response = self.client.get(reverse('admin:orders_promocode_change', args=[promo_code.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.order_number)

    def test_promo_code_admin_form_normalizes_code(self):
        form = PromoCodeAdminForm(data={
            'code': ' summer10 ',
            'discount_type': PromoCode.DiscountType.PERCENT,
            'value': '10.00',
            'used_count': '0',
            'is_active': 'on',
        })

        self.assertTrue(form.is_valid(), form.errors)
        promo_code = form.save()
        self.assertEqual(promo_code.code, 'SUMMER10')

    def test_promo_code_admin_form_rejects_invalid_percent(self):
        form = PromoCodeAdminForm(data={
            'code': 'TOO-MUCH',
            'discount_type': PromoCode.DiscountType.PERCENT,
            'value': '101.00',
            'used_count': '0',
            'is_active': 'on',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('value', form.errors)

    def test_promo_code_admin_form_rejects_invalid_date_range(self):
        form = PromoCodeAdminForm(data={
            'code': 'DATES',
            'discount_type': PromoCode.DiscountType.FIXED,
            'value': '100.00',
            'used_count': '0',
            'valid_from': '2026-06-12 12:00:00',
            'valid_until': '2026-06-11 12:00:00',
            'is_active': 'on',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('valid_until', form.errors)

    def test_promo_code_admin_used_count_is_readonly(self):
        model_admin = PromoCodeAdmin(PromoCode, admin.site)

        self.assertIn('used_count', model_admin.get_readonly_fields(request=None))

    def test_promo_code_admin_remaining_uses_display(self):
        model_admin = PromoCodeAdmin(PromoCode, admin.site)
        promo_code = PromoCode.objects.create(
            code='LIMITED',
            discount_type=PromoCode.DiscountType.FIXED,
            value=Decimal('100.00'),
            usage_limit=5,
            used_count=2,
        )

        self.assertEqual(model_admin.remaining_uses(promo_code), 3)

    def test_promo_code_usage_admin_is_readonly(self):
        model_admin = PromoCodeUsageAdmin(PromoCodeUsage, admin.site)

        self.assertFalse(model_admin.has_add_permission(request=None))
        self.assertFalse(model_admin.has_change_permission(request=None, obj=object()))
        self.assertFalse(model_admin.has_delete_permission(request=None, obj=object()))

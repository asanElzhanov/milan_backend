import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import (
    Banner,
    Brand,
    Category,
    Color,
    Product,
    ProductVariant,
    Review,
    Size,
    StockMovement,
)
from apps.catalog.services import (
    DuplicateReviewError,
    ProductReviewService,
    ReviewModerationService,
    StockService,
)
from apps.cms.models import StaticPage
from apps.notifications.models import Notification
from apps.orders.models import Cart, DeliveryMethod, Order, PromoCode, PromoCodeUsage
from apps.orders.services import CartService, CheckoutService, OrderStatusService


class Command(BaseCommand):
    help = 'Seed idempotent development/demo data for the shop.'

    ADMIN_EMAIL = 'seed.admin@example.com'
    MANAGER_EMAIL = 'seed.manager@example.com'
    CUSTOMER_EMAIL = 'seed.customer@example.com'

    PRODUCT_SKUS = {
        'SEED-NIKE-AIR-001',
        'SEED-ADIDAS-RUN-001',
        'SEED-PUMA-HOODIE-001',
        'SEED-LOCAL-BAG-001',
        'SEED-NIKE-CAP-001',
        'SEED-INACTIVE-001',
    }
    VARIANT_SKUS = {
        'SEED-NIKE-AIR-BLK-41',
        'SEED-NIKE-AIR-BLK-42',
        'SEED-NIKE-AIR-WHT-41',
        'SEED-NIKE-AIR-WHT-42',
        'SEED-ADIDAS-RUN-BLU-42',
        'SEED-ADIDAS-RUN-RED-43',
        'SEED-PUMA-HOODIE-BLK-M',
        'SEED-PUMA-HOODIE-BLK-L',
        'SEED-LOCAL-BAG-BLU-OS',
        'SEED-NIKE-CAP-WHT-OS',
        'SEED-INACTIVE-BLK-40',
    }
    ORDER_NUMBERS = {'SEED-ORDER-0001', 'SEED-ORDER-0002', 'SEED-ORDER-0003'}
    PROMO_CODES = {'SEED10', 'SEEDFIXED', 'SEEDEXPIRED', 'SEEDINACTIVE', 'SEEDMIN'}
    PAGE_SLUGS = {'about', 'delivery', 'returns', 'privacy-policy'}
    BANNER_TITLES = {'Seed Homepage Hero', 'Seed Mid Season Promo'}
    NOTIFICATION_TITLES = {
        'Seed manager notification',
        'Seed admin notification',
        'Seed customer notification',
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Destructive: remove demo data created by this command before seeding.',
        )
        size_group = parser.add_mutually_exclusive_group()
        size_group.add_argument('--small', action='store_true', help='Seed a smaller product set.')
        size_group.add_argument('--full', action='store_true', help='Seed the full demo product set.')
        parser.add_argument('--with-demo-orders', action='store_true')
        parser.add_argument('--with-demo-reviews', action='store_true')
        parser.add_argument('--with-demo-notifications', action='store_true')

    def handle(self, *args, **options):
        self.counts = defaultdict(int)
        self.demo_passwords = {}
        self.options = options

        with transaction.atomic():
            if options['reset']:
                self.stdout.write(self.style.WARNING(
                    '--reset is destructive and removes only seed_data demo records.'
                ))
                self.reset_demo_data()

            self.seed_users()
            self.seed_catalog_dictionaries()
            self.seed_products(full=options['full'] or not options['small'])
            self.seed_delivery_methods()
            self.seed_promo_codes()
            self.seed_cms()

            if options['with_demo_orders']:
                self.seed_orders()
            if options['with_demo_reviews']:
                self.seed_reviews()
            if options['with_demo_notifications']:
                self.seed_notifications()

        self.print_summary()

    def reset_demo_data(self):
        Review.objects.filter(
            user__email=self.CUSTOMER_EMAIL,
            product__sku__in=self.PRODUCT_SKUS,
        ).delete()
        Order.objects.filter(order_number__in=self.ORDER_NUMBERS).delete()
        Cart.objects.filter(user__email__in=self.demo_emails()).delete()
        Notification.objects.filter(title__in=self.NOTIFICATION_TITLES).delete()
        PromoCode.objects.filter(code__in=self.PROMO_CODES).delete()

        demo_variants = ProductVariant.objects.filter(sku__in=self.VARIANT_SKUS)
        StockMovement.objects.filter(variant__in=demo_variants).delete()
        Product.objects.filter(sku__in=self.PRODUCT_SKUS).delete()

        Banner.objects.filter(title_ru__in=self.BANNER_TITLES).delete()
        StaticPage.objects.filter(slug__in=self.PAGE_SLUGS).delete()
        User.objects.filter(email__in=self.demo_emails()).delete()
        self.counts['reset'] += 1

    def seed_users(self):
        users = [
            {
                'email': self.ADMIN_EMAIL,
                'env': 'SEED_ADMIN_PASSWORD',
                'default': 'seed-admin-dev',
                'fields': {
                    'first_name': 'Seed',
                    'last_name': 'Admin',
                    'role': User.Role.ADMIN,
                    'is_staff': True,
                    'is_superuser': True,
                    'is_active': True,
                    'is_email_verified': True,
                },
            },
            {
                'email': self.MANAGER_EMAIL,
                'env': 'SEED_MANAGER_PASSWORD',
                'default': 'seed-manager-dev',
                'fields': {
                    'first_name': 'Seed',
                    'last_name': 'Manager',
                    'role': User.Role.MANAGER,
                    'is_staff': True,
                    'is_superuser': False,
                    'is_active': True,
                    'is_email_verified': True,
                },
            },
            {
                'email': self.CUSTOMER_EMAIL,
                'env': 'SEED_CUSTOMER_PASSWORD',
                'default': 'seed-customer-dev',
                'fields': {
                    'first_name': 'Demo',
                    'last_name': 'Customer',
                    'role': User.Role.CUSTOMER,
                    'is_staff': False,
                    'is_superuser': False,
                    'is_active': True,
                    'is_email_verified': True,
                },
            },
        ]
        for item in users:
            password = os.environ.get(item['env'])
            if not password:
                password = item['default']
                self.stdout.write(self.style.WARNING(
                    f'{item["env"]} is not set; using development-only default.'
                ))
            user, created = User.objects.update_or_create(
                email=item['email'],
                defaults=item['fields'],
            )
            user.set_password(password)
            user.save()
            self.demo_passwords[item['email']] = password
            self.bump('users', created)

    def seed_catalog_dictionaries(self):
        self.categories = {}
        category_specs = [
            ('men', 'Men', None, 10),
            ('women', 'Women', None, 20),
            ('shoes', 'Shoes', None, 30),
            ('accessories', 'Accessories', None, 40),
            ('men-shoes', 'Men Shoes', 'men', 10),
            ('women-shoes', 'Women Shoes', 'women', 10),
            ('sneakers', 'Sneakers', 'shoes', 10),
            ('bags', 'Bags', 'accessories', 10),
            ('caps', 'Caps', 'accessories', 20),
        ]
        for slug, name, parent_slug, sort_order in category_specs:
            parent = self.categories.get(parent_slug)
            category, created = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    'name_ru': name,
                    'name_en': name,
                    'parent': parent,
                    'is_active': True,
                    'sort_order': sort_order,
                    'seo_title': f'{name} | Demo catalog',
                    'seo_description': f'Demo category for {name.lower()}.',
                },
            )
            self.categories[slug] = category
            self.bump('categories', created)

        self.brands = {}
        for name, slug in (
            ('Nike', 'nike'),
            ('Adidas', 'adidas'),
            ('Puma', 'puma'),
            ('Local Brand', 'local-brand'),
        ):
            brand, created = Brand.objects.update_or_create(
                slug=slug,
                defaults={'name_ru': name, 'name_en': name, 'is_active': True},
            )
            self.brands[slug] = brand
            self.bump('brands', created)

        self.colors = {}
        for name, slug, hex_code in (
            ('Black', 'black', '#000000'),
            ('White', 'white', '#FFFFFF'),
            ('Red', 'red', '#FF0000'),
            ('Blue', 'blue', '#0000FF'),
        ):
            color, created = Color.objects.update_or_create(
                slug=slug,
                defaults={'name_ru': name, 'name_en': name, 'hex_code': hex_code, 'is_active': True},
            )
            self.colors[slug] = color
            self.bump('colors', created)

        self.sizes = {}
        for size_type, values in (
            (Size.SizeType.CLOTHES, ['S', 'M', 'L', 'XL']),
            (Size.SizeType.SHOES, ['40', '41', '42', '43']),
            (Size.SizeType.ACCESSORIES, ['One Size']),
        ):
            for index, value in enumerate(values, start=1):
                size, created = Size.objects.update_or_create(
                    value=value,
                    size_type=size_type,
                    defaults={'sort_order': index, 'is_active': True},
                )
                self.sizes[(size_type, value)] = size
                self.bump('sizes', created)

    def seed_products(self, *, full):
        product_specs = self.product_specs()
        if not full:
            product_specs = product_specs[:3]

        self.products = {}
        self.variants = {}
        for spec in product_specs:
            product, created = Product.objects.update_or_create(
                sku=spec['sku'],
                defaults={
                    'name_ru': spec['name'],
                    'name_en': spec['name'],
                    'slug': spec['slug'],
                    'category': self.categories[spec['category']],
                    'brand': self.brands[spec['brand']],
                    'description_ru': spec['description'],
                    'description_en': spec['description'],
                    'composition_ru': spec.get('composition', ''),
                    'material_ru': spec.get('material', ''),
                    'season': spec.get('season', Product.Season.ALL_SEASON),
                    'price': spec['price'],
                    'old_price': spec.get('old_price'),
                    'is_active': spec.get('is_active', True),
                    'is_new': spec.get('is_new', False),
                    'is_featured': spec.get('is_featured', False),
                    'seo_title': f'{spec["name"]} | Demo shop',
                    'seo_description': spec['description'],
                    'meta_title': f'{spec["name"]} | Demo shop',
                    'meta_description': spec['description'],
                },
            )
            self.products[spec['sku']] = product
            self.bump('products', created)

            for variant_spec in spec['variants']:
                variant, variant_created = ProductVariant.objects.update_or_create(
                    sku=variant_spec['sku'],
                    defaults={
                        'product': product,
                        'color': self.colors.get(variant_spec.get('color')),
                        'size': self.sizes.get(variant_spec.get('size')),
                        'variant_price': variant_spec.get('variant_price'),
                        'is_active': variant_spec.get('is_active', True),
                    },
                )
                self.sync_stock(variant, variant_spec['stock'])
                self.variants[variant.sku] = variant
                self.bump('variants', variant_created)

    def seed_delivery_methods(self):
        specs = [
            {
                'code': 'courier',
                'name_ru': 'Courier delivery',
                'name_en': 'Courier delivery',
                'delivery_type': DeliveryMethod.DeliveryType.COURIER,
                'price_type': DeliveryMethod.PriceType.FIXED,
                'base_price': Decimal('1500.00'),
                'free_from_amount': Decimal('30000.00'),
                'sort_order': 10,
            },
            {
                'code': 'pickup',
                'name_ru': 'Pickup',
                'name_en': 'Pickup',
                'delivery_type': DeliveryMethod.DeliveryType.PICKUP,
                'price_type': DeliveryMethod.PriceType.FREE,
                'base_price': Decimal('0.00'),
                'free_from_amount': None,
                'sort_order': 20,
            },
            {
                'code': 'kazakhstan_delivery',
                'name_ru': 'Kazakhstan delivery',
                'name_en': 'Kazakhstan delivery',
                'delivery_type': DeliveryMethod.DeliveryType.KAZAKHSTAN_DELIVERY,
                'price_type': DeliveryMethod.PriceType.MANAGER_CALCULATION,
                'base_price': Decimal('0.00'),
                'free_from_amount': None,
                'sort_order': 30,
            },
        ]
        for spec in specs:
            method, created = DeliveryMethod.objects.update_or_create(
                code=spec['code'],
                defaults={
                    **spec,
                    'slug': spec['code'],
                    'description_ru': f'Demo {spec["name_ru"].lower()} method.',
                    'is_active': True,
                },
            )
            self.bump('delivery_methods', created)

    def seed_promo_codes(self):
        now = timezone.now()
        specs = [
            {
                'code': 'SEED10',
                'discount_type': PromoCode.DiscountType.PERCENT,
                'value': Decimal('10.00'),
                'min_order_amount': None,
                'usage_limit': 100,
                'used_count': 0,
                'valid_from': now,
                'valid_until': now + timedelta(days=90),
                'is_active': True,
            },
            {
                'code': 'SEEDFIXED',
                'discount_type': PromoCode.DiscountType.FIXED,
                'value': Decimal('2500.00'),
                'min_order_amount': None,
                'usage_limit': 100,
                'used_count': 0,
                'valid_from': now,
                'valid_until': now + timedelta(days=90),
                'is_active': True,
            },
            {
                'code': 'SEEDEXPIRED',
                'discount_type': PromoCode.DiscountType.PERCENT,
                'value': Decimal('15.00'),
                'min_order_amount': None,
                'usage_limit': 100,
                'used_count': 0,
                'valid_from': now - timedelta(days=30),
                'valid_until': now - timedelta(days=1),
                'is_active': True,
            },
            {
                'code': 'SEEDINACTIVE',
                'discount_type': PromoCode.DiscountType.FIXED,
                'value': Decimal('1000.00'),
                'min_order_amount': None,
                'usage_limit': 100,
                'used_count': 0,
                'valid_from': now,
                'valid_until': now + timedelta(days=90),
                'is_active': False,
            },
            {
                'code': 'SEEDMIN',
                'discount_type': PromoCode.DiscountType.PERCENT,
                'value': Decimal('20.00'),
                'min_order_amount': Decimal('50000.00'),
                'usage_limit': 100,
                'used_count': 0,
                'valid_from': now,
                'valid_until': now + timedelta(days=90),
                'is_active': True,
            },
        ]
        for spec in specs:
            promo, created = PromoCode.objects.update_or_create(
                code=spec['code'],
                defaults=spec,
            )
            self.bump('promo_codes', created)

    def seed_cms(self):
        for page in (
            ('about', 'About', 'About the demo shop.'),
            ('delivery', 'Delivery', 'Delivery terms for demo customers.'),
            ('returns', 'Returns', 'Return policy for demo purchases.'),
            ('privacy-policy', 'Privacy Policy', 'Demo privacy policy.'),
        ):
            obj, created = StaticPage.objects.update_or_create(
                slug=page[0],
                defaults={
                    'title_ru': page[1],
                    'title_en': page[1],
                    'content_ru': page[2],
                    'content_en': page[2],
                    'seo_title': f'{page[1]} | Demo shop',
                    'seo_description': page[2],
                    'is_active': True,
                },
            )
            self.bump('static_pages', created)

        for title, position, sort_order in (
            ('Seed Homepage Hero', Banner.Position.HERO, 10),
            ('Seed Mid Season Promo', Banner.Position.PROMO, 20),
        ):
            banner, created = Banner.objects.update_or_create(
                title_ru=title,
                defaults={
                    'title_en': title,
                    'subtitle_ru': 'Demo banner created by seed_data.',
                    'subtitle_en': 'Demo banner created by seed_data.',
                    'button_text_ru': 'Shop now',
                    'button_text_en': 'Shop now',
                    'image': f'seed/banners/{title.lower().replace(" ", "-")}.png',
                    'link': '/catalog/products/',
                    'position': position,
                    'is_active': True,
                    'sort_order': sort_order,
                },
            )
            self.bump('banners', created)

    def seed_orders(self):
        customer = User.objects.get(email=self.CUSTOMER_EMAIL)
        order_specs = [
            {
                'order_number': 'SEED-ORDER-0001',
                'variant_skus': [('SEED-NIKE-AIR-BLK-41', 1), ('SEED-LOCAL-BAG-BLU-OS', 1)],
                'delivery_method': 'courier',
                'promo_code': 'SEED10',
                'status': Order.Status.COMPLETED,
            },
            {
                'order_number': 'SEED-ORDER-0002',
                'variant_skus': [('SEED-PUMA-HOODIE-BLK-M', 1)],
                'delivery_method': 'pickup',
                'promo_code': None,
                'status': Order.Status.CANCELLED,
            },
            {
                'order_number': 'SEED-ORDER-0003',
                'variant_skus': [('SEED-ADIDAS-RUN-BLU-42', 1)],
                'delivery_method': 'kazakhstan_delivery',
                'promo_code': 'SEEDFIXED',
                'status': Order.Status.PAID,
            },
        ]
        for spec in order_specs:
            order = Order.objects.filter(order_number=spec['order_number']).first()
            if order:
                self.apply_existing_order_stock_effect(order)
                self.counts['orders_updated'] += 1
                continue

            cart = CartService.get_or_create_user_cart(customer)
            CartService.clear_cart(cart)
            for sku, quantity in spec['variant_skus']:
                CartService.add_item(cart, ProductVariant.objects.get(sku=sku), quantity)

            order = CheckoutService.checkout(
                cart=cart,
                user=customer,
                customer_name=customer.full_name or 'Demo Customer',
                phone='+77010000000',
                email=customer.email,
                city='Almaty',
                delivery_address='Seed demo street 10',
                delivery_method=spec['delivery_method'],
                promo_code=spec['promo_code'],
                comment='Demo order created by seed_data.',
            )
            old_number = order.order_number
            order.order_number = spec['order_number']
            order.save(update_fields=['order_number', 'updated_at'])
            StockMovement.objects.filter(comment=f'Заказ #{old_number}').update(
                comment=f'Заказ #{order.order_number}'
            )
            self.move_order_to_status(order, spec['status'])
            self.counts['orders_created'] += 1
        self.recalculate_seed_promo_usage_counts()

    def recalculate_seed_promo_usage_counts(self):
        for promo_code in PromoCode.objects.filter(code__in=self.PROMO_CODES):
            used_count = PromoCodeUsage.objects.filter(promo_code=promo_code).count()
            if promo_code.used_count != used_count:
                promo_code.used_count = used_count
                promo_code.save(update_fields=['used_count', 'updated_at'])

    def apply_existing_order_stock_effect(self, order):
        if order.status == Order.Status.CANCELLED:
            return
        for item in order.items.select_related('variant'):
            variant = item.variant
            variant.refresh_from_db()
            desired_quantity = max(variant.stock_quantity - item.quantity, 0)
            if variant.stock_quantity == desired_quantity:
                continue
            StockService.manual_adjustment(
                variant=variant,
                new_quantity=desired_quantity,
                user=User.objects.filter(email=self.MANAGER_EMAIL).first(),
                comment=f'seed_data existing order #{order.order_number}',
            )

    def seed_reviews(self):
        self.seed_orders()
        customer = User.objects.get(email=self.CUSTOMER_EMAIL)
        manager = User.objects.get(email=self.MANAGER_EMAIL)
        specs = [
            ('SEED-ORDER-0001', 'SEED-NIKE-AIR-001', 5, 'Published demo review.', Review.Status.PUBLISHED),
            ('SEED-ORDER-0001', 'SEED-LOCAL-BAG-001', 4, 'Pending demo review.', Review.Status.PENDING),
            ('SEED-ORDER-0003', 'SEED-ADIDAS-RUN-001', 2, 'Rejected demo review.', Review.Status.REJECTED),
        ]
        for order_number, product_sku, rating, text, status in specs:
            order = Order.objects.get(order_number=order_number)
            product = Product.objects.get(sku=product_sku)
            review = Review.objects.filter(product=product, user=customer, order=order).first()
            if review is None:
                try:
                    review = ProductReviewService.create_review(
                        user=customer,
                        product=product,
                        order=order,
                        rating=rating,
                        text=text,
                    )
                    self.counts['reviews_created'] += 1
                except DuplicateReviewError:
                    review = Review.objects.get(product=product, user=customer, order=order)
            else:
                review.rating = rating
                review.text = text
                review.save(update_fields=['rating', 'text', 'updated_at'])
                self.counts['reviews_updated'] += 1

            if status == Review.Status.PUBLISHED and review.status != status:
                ReviewModerationService.publish_review(review, manager, comment='Seed approved.')
            elif status == Review.Status.REJECTED and review.status != status:
                ReviewModerationService.reject_review(review, manager, comment='Seed rejected.')

    def seed_notifications(self):
        admin = User.objects.get(email=self.ADMIN_EMAIL)
        manager = User.objects.get(email=self.MANAGER_EMAIL)
        customer = User.objects.get(email=self.CUSTOMER_EMAIL)
        specs = [
            (manager, 'Seed manager notification', 'Demo manager notification.'),
            (admin, 'Seed admin notification', 'Demo admin notification.'),
            (customer, 'Seed customer notification', 'Demo customer notification.'),
        ]
        for recipient, title, message in specs:
            notification, created = Notification.objects.update_or_create(
                recipient=recipient,
                title=title,
                defaults={
                    'role': None,
                    'message': message,
                    'event_type': Notification.EventType.SYSTEM,
                    'is_read': False,
                },
            )
            self.bump('notifications', created)

    def sync_stock(self, variant, desired_quantity):
        variant.refresh_from_db()
        if variant.stock_quantity == desired_quantity:
            return
        StockService.manual_adjustment(
            variant=variant,
            new_quantity=desired_quantity,
            user=User.objects.filter(email=self.MANAGER_EMAIL).first(),
            comment='seed_data initial stock',
        )

    def move_order_to_status(self, order, status):
        manager = User.objects.get(email=self.MANAGER_EMAIL)
        order.refresh_from_db()
        if status == Order.Status.NEW:
            return
        if status == Order.Status.CANCELLED:
            OrderStatusService.cancel_order(order, changed_by=manager, comment='Seed cancellation.')
            return
        if status in {
            Order.Status.PAID,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
        }:
            OrderStatusService.mark_paid(order, changed_by=manager, comment='Seed paid.')
        if status == Order.Status.PROCESSING:
            return OrderStatusService.change_status(order, status, changed_by=manager, comment='Seed processing.')
        if status == Order.Status.SHIPPED:
            OrderStatusService.change_status(order, Order.Status.PROCESSING, changed_by=manager, comment='Seed processing.')
            return OrderStatusService.change_status(order, status, changed_by=manager, comment='Seed shipped.')
        if status == Order.Status.COMPLETED:
            OrderStatusService.change_status(order, Order.Status.PROCESSING, changed_by=manager, comment='Seed processing.')
            OrderStatusService.change_status(order, Order.Status.SHIPPED, changed_by=manager, comment='Seed shipped.')
            return OrderStatusService.change_status(order, status, changed_by=manager, comment='Seed completed.')
        if status == Order.Status.RETURNED:
            self.move_order_to_status(order, Order.Status.COMPLETED)
            return OrderStatusService.change_status(order, status, changed_by=manager, comment='Seed returned.')
        return None

    def product_specs(self):
        shoe_41 = (Size.SizeType.SHOES, '41')
        shoe_42 = (Size.SizeType.SHOES, '42')
        shoe_43 = (Size.SizeType.SHOES, '43')
        shoe_40 = (Size.SizeType.SHOES, '40')
        clothes_m = (Size.SizeType.CLOTHES, 'M')
        clothes_l = (Size.SizeType.CLOTHES, 'L')
        one_size = (Size.SizeType.ACCESSORIES, 'One Size')
        return [
            {
                'sku': 'SEED-NIKE-AIR-001',
                'name': 'Nike Air Demo',
                'slug': 'seed-nike-air-demo',
                'category': 'sneakers',
                'brand': 'nike',
                'description': 'Multi-variant demo sneaker.',
                'material': 'Textile',
                'price': Decimal('42000.00'),
                'old_price': Decimal('52000.00'),
                'is_new': True,
                'is_featured': True,
                'variants': [
                    {'sku': 'SEED-NIKE-AIR-BLK-41', 'color': 'black', 'size': shoe_41, 'stock': 12},
                    {'sku': 'SEED-NIKE-AIR-BLK-42', 'color': 'black', 'size': shoe_42, 'stock': 8},
                    {'sku': 'SEED-NIKE-AIR-WHT-41', 'color': 'white', 'size': shoe_41, 'stock': 10},
                    {'sku': 'SEED-NIKE-AIR-WHT-42', 'color': 'white', 'size': shoe_42, 'stock': 7},
                ],
            },
            {
                'sku': 'SEED-ADIDAS-RUN-001',
                'name': 'Adidas Run Demo',
                'slug': 'seed-adidas-run-demo',
                'category': 'men-shoes',
                'brand': 'adidas',
                'description': 'Lightweight running shoes for demo data.',
                'material': 'Mesh',
                'price': Decimal('38000.00'),
                'variants': [
                    {'sku': 'SEED-ADIDAS-RUN-BLU-42', 'color': 'blue', 'size': shoe_42, 'stock': 9},
                    {'sku': 'SEED-ADIDAS-RUN-RED-43', 'color': 'red', 'size': shoe_43, 'stock': 5},
                ],
            },
            {
                'sku': 'SEED-PUMA-HOODIE-001',
                'name': 'Puma Hoodie Demo',
                'slug': 'seed-puma-hoodie-demo',
                'category': 'men',
                'brand': 'puma',
                'description': 'Comfort hoodie used for demo catalog data.',
                'material': 'Cotton',
                'price': Decimal('24000.00'),
                'is_new': True,
                'variants': [
                    {'sku': 'SEED-PUMA-HOODIE-BLK-M', 'color': 'black', 'size': clothes_m, 'stock': 15},
                    {'sku': 'SEED-PUMA-HOODIE-BLK-L', 'color': 'black', 'size': clothes_l, 'stock': 11},
                ],
            },
            {
                'sku': 'SEED-LOCAL-BAG-001',
                'name': 'Local Brand Tote Demo',
                'slug': 'seed-local-brand-tote-demo',
                'category': 'bags',
                'brand': 'local-brand',
                'description': 'Local accessory demo product.',
                'material': 'Canvas',
                'price': Decimal('12000.00'),
                'variants': [
                    {'sku': 'SEED-LOCAL-BAG-BLU-OS', 'color': 'blue', 'size': one_size, 'stock': 20},
                ],
            },
            {
                'sku': 'SEED-NIKE-CAP-001',
                'name': 'Nike Cap Demo',
                'slug': 'seed-nike-cap-demo',
                'category': 'caps',
                'brand': 'nike',
                'description': 'One size cap demo product.',
                'price': Decimal('9000.00'),
                'old_price': Decimal('11000.00'),
                'variants': [
                    {'sku': 'SEED-NIKE-CAP-WHT-OS', 'color': 'white', 'size': one_size, 'stock': 14},
                ],
            },
            {
                'sku': 'SEED-INACTIVE-001',
                'name': 'Inactive Seed Product',
                'slug': 'seed-inactive-product',
                'category': 'sneakers',
                'brand': 'puma',
                'description': 'Inactive product for admin/demo filtering.',
                'price': Decimal('10000.00'),
                'is_active': False,
                'variants': [
                    {
                        'sku': 'SEED-INACTIVE-BLK-40',
                        'color': 'black',
                        'size': shoe_40,
                        'stock': 0,
                        'is_active': False,
                    },
                ],
            },
        ]

    def bump(self, key, created):
        suffix = 'created' if created else 'updated'
        self.counts[f'{key}_{suffix}'] += 1

    def demo_emails(self):
        return {self.ADMIN_EMAIL, self.MANAGER_EMAIL, self.CUSTOMER_EMAIL}

    def print_summary(self):
        self.stdout.write(self.style.SUCCESS('seed_data completed.'))
        for key in sorted(self.counts):
            self.stdout.write(f'  {key}: {self.counts[key]}')

        self.stdout.write('Demo credentials:')
        for email, password in self.demo_passwords.items():
            self.stdout.write(f'  {email} / {password}')

        self.stdout.write('Useful endpoints:')
        self.stdout.write('  /api/v1/catalog/products/')
        self.stdout.write('  /api/v1/orders/delivery-methods/')
        self.stdout.write('  /api/v1/catalog/banners/')

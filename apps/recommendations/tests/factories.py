from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.orders.models import Cart, DeliveryMethod, Order, OrderItem


_sequence = 0


def next_number():
    global _sequence
    _sequence += 1
    return _sequence


def make_user(**kwargs):
    number = next_number()
    defaults = {'email': f'user-{number}@example.com', 'password': 'test-pass-123'}
    defaults.update(kwargs)
    password = defaults.pop('password')
    return get_user_model().objects.create_user(password=password, **defaults)


def make_category(parent=None, **kwargs):
    number = next_number()
    defaults = {'name_ru': f'Category {number}', 'slug': f'category-{number}', 'parent': parent}
    defaults.update(kwargs)
    return Category.objects.create(**defaults)


def make_product(category=None, *, with_variant=True, stock=10, variant_active=True, **kwargs):
    number = next_number()
    category = category or make_category()
    defaults = {
        'sku': f'PRODUCT-{number}',
        'name_ru': f'Product {number}',
        'slug': f'product-{number}',
        'category': category,
        'price': Decimal('100.00'),
    }
    defaults.update(kwargs)
    product = Product.objects.create(**defaults)
    if with_variant:
        ProductVariant.objects.create(
            product=product,
            sku=f'VARIANT-{number}',
            stock_quantity=stock,
            is_active=variant_active,
        )
    return product


def make_brand(**kwargs):
    number = next_number()
    defaults = {'name_ru': f'Brand {number}', 'slug': f'brand-{number}'}
    defaults.update(kwargs)
    return Brand.objects.create(**defaults)


def make_cart(user=None):
    return Cart.objects.create(user=user)


def make_delivery_method(**kwargs):
    number = next_number()
    defaults = {
        'name_ru': f'Delivery {number}',
        'code': f'delivery-{number}',
        'slug': f'delivery-{number}',
        'delivery_type': DeliveryMethod.DeliveryType.COURIER,
        'price_type': DeliveryMethod.PriceType.FREE,
    }
    defaults.update(kwargs)
    return DeliveryMethod.objects.create(**defaults)


def make_order(user=None, *, status=Order.Status.NEW, payment_status=Order.PaymentStatus.UNPAID):
    number = next_number()
    return Order.objects.create(
        user=user,
        customer_name='Test User',
        phone='+77000000000',
        email=f'order-{number}@example.com',
        delivery_method=Order.DeliveryMethod.COURIER,
        total_amount=Decimal('100.00'),
        items_total=Decimal('100.00'),
        status=status,
        payment_status=payment_status,
    )


def add_order_item(order, product, quantity=1):
    variant = product.variants.first()
    return OrderItem.objects.create(
        order=order,
        variant=variant,
        product_name=product.name_ru,
        product_slug=product.slug,
        sku=variant.sku,
        unit_price=product.price,
        quantity=quantity,
        total_price=product.price * quantity,
    )

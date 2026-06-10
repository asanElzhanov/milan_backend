from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.catalog.models import Brand, Category, Color, Product, ProductVariant, Size


class ProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Shoes', slug='shoes')
        self.brand = Brand.objects.create(name='Nike', slug='nike')
        self.color = Color.objects.create(name='Black', slug='black', hex_code='#000000')
        self.size = Size.objects.create(value='42', size_type=Size.SizeType.SHOES)

    def make_product(self, **kwargs):
        data = {
            'sku': 'SKU-1',
            'name': 'Air Max',
            'category': self.category,
            'brand': self.brand,
            'price': Decimal('100.00'),
        }
        data.update(kwargs)
        return Product(**data)

    def test_generates_unique_slug_from_name(self):
        first = self.make_product()
        first.save()
        second = self.make_product(sku='SKU-2')
        second.save()

        self.assertEqual(first.slug, 'air-max')
        self.assertEqual(second.slug, 'air-max-2')

    def test_rejects_negative_price(self):
        product = self.make_product(price=Decimal('-1.00'))

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_rejects_old_price_lower_than_price(self):
        product = self.make_product(price=Decimal('100.00'), old_price=Decimal('90.00'))

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_discount_and_is_sale_are_computed_from_prices(self):
        product = self.make_product(price=Decimal('80.00'), old_price=Decimal('100.00'))

        self.assertEqual(product.discount, 20)
        self.assertEqual(product.discount_percent, 20)
        self.assertTrue(product.is_sale)

    def test_variant_uses_product_price_when_variant_price_is_empty(self):
        product = self.make_product()
        product.save()
        variant = ProductVariant.objects.create(
            product=product,
            color=self.color,
            size=self.size,
            sku='VAR-1',
            stock_quantity=3,
        )

        self.assertEqual(variant.final_price, product.price)

    def test_variant_price_overrides_product_price(self):
        product = self.make_product()
        product.save()
        variant = ProductVariant.objects.create(
            product=product,
            color=self.color,
            size=self.size,
            sku='VAR-2',
            stock_quantity=3,
            variant_price=Decimal('120.00'),
        )

        self.assertEqual(variant.final_price, Decimal('120.00'))

    def test_variant_in_stock_requires_quantity_and_active_status(self):
        product = self.make_product()
        product.save()
        variant = ProductVariant(
            product=product,
            color=self.color,
            size=self.size,
            sku='VAR-3',
            stock_quantity=1,
            is_active=False,
        )

        self.assertFalse(variant.in_stock)

    def test_variant_rejects_negative_variant_price(self):
        product = self.make_product()
        product.save()
        variant = ProductVariant(
            product=product,
            color=self.color,
            size=self.size,
            sku='VAR-4',
            stock_quantity=1,
            variant_price=Decimal('-1.00'),
        )

        with self.assertRaises(ValidationError):
            variant.full_clean()

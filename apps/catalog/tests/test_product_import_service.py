import csv
import io
from decimal import Decimal
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.catalog.import_services import ProductImportService
from apps.catalog.models import (
    Brand, Category, Color, ImportJob, ImportJobError,
    Product, ProductVariant, Size, StockMovement,
)


class ProductImportServiceTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.user = User.objects.create_user(
            email='import-manager@example.com',
            role=User.Role.MANAGER,
        )
        self.category = Category.objects.create(name_ru='Shoes', slug='shoes')
        self.brand = Brand.objects.create(name_ru='Nike', slug='nike')
        self.color = Color.objects.create(name_ru='Black', slug='black', hex_code='#000000')
        self.size = Size.objects.create(value='42', size_type=Size.SizeType.SHOES)

    def make_job(self, content=''):
        return ImportJob.objects.create(
            file=SimpleUploadedFile(
                'products.csv',
                content.encode('utf-8'),
                content_type='text/csv',
            ),
            created_by=self.user,
        )

    def valid_row(self, **overrides):
        row = {
            'product_name': 'Air Max',
            'product_slug': 'air-max',
            'category_slug': self.category.slug,
            'brand_slug': self.brand.slug,
            'price': '100.00',
            'old_price': '120.00',
            'is_new': 'yes',
            'is_active': 'true',
            'size_value': self.size.value,
            'size_type': self.size.size_type,
            'color_slug': self.color.slug,
            'sku': 'AIR-MAX-BLACK-42',
            'stock_quantity': '5',
            'variant_price': '110.00',
            'variant_is_active': '1',
        }
        row.update(overrides)
        return row

    def test_valid_row_creates_product_variant_and_stock_movement(self):
        job = self.make_job()

        result = ProductImportService.process_row(self.valid_row(), 2, job)

        self.assertTrue(result.success)
        product = Product.objects.get(slug='air-max')
        self.assertEqual(product.name_ru, 'Air Max')
        self.assertEqual(product.category, self.category)
        self.assertEqual(product.brand, self.brand)
        self.assertEqual(product.price, Decimal('100.00'))
        self.assertTrue(product.is_new)
        variant = ProductVariant.objects.get(sku='AIR-MAX-BLACK-42')
        self.assertEqual(variant.product, product)
        self.assertEqual(variant.color, self.color)
        self.assertEqual(variant.size, self.size)
        self.assertEqual(variant.stock_quantity, 5)
        self.assertEqual(variant.variant_price, Decimal('110.00'))
        movement = StockMovement.objects.get(variant=variant)
        self.assertEqual(movement.quantity, 5)
        self.assertEqual(movement.operation_type, StockMovement.OperationType.MANUAL_ADJUSTMENT)
        self.assertEqual(movement.user, self.user)

    def test_missing_required_header_fails_validation(self):
        result = ProductImportService.validate_headers(['product_name', 'price', 'sku'])

        self.assertEqual(result['missing'], ['category_slug', 'stock_quantity'])
        self.assertEqual(result['unknown'], [])

    def test_invalid_price_creates_row_error(self):
        job = self.make_job()

        result = ProductImportService.process_row(self.valid_row(price='-1.00'), 2, job)

        self.assertFalse(result.success)
        error = ImportJobError.objects.get(import_job=job)
        self.assertEqual(error.row_number, 2)
        self.assertIn('price', error.field_errors)
        self.assertFalse(Product.objects.exists())

    def test_invalid_category_creates_row_error(self):
        job = self.make_job()

        result = ProductImportService.process_row(
            self.valid_row(category_slug='missing-category'),
            2,
            job,
        )

        self.assertFalse(result.success)
        error = ImportJobError.objects.get(import_job=job)
        self.assertIn('category_slug', error.field_errors)
        self.assertFalse(Product.objects.exists())

    def test_existing_sku_updates_variant(self):
        product = Product.objects.create(
            sku='PRODUCT-OLD',
            name_ru='Old Name',
            slug='old-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('90.00'),
        )
        variant = ProductVariant.objects.create(
            product=product,
            color=self.color,
            size=self.size,
            sku='EXISTING-SKU',
            stock_quantity=2,
            variant_price=Decimal('95.00'),
        )
        job = self.make_job()

        result = ProductImportService.process_row(
            self.valid_row(
                product_name='Updated Name',
                product_slug='',
                sku='EXISTING-SKU',
                stock_quantity='8',
                variant_price='105.00',
            ),
            2,
            job,
        )

        self.assertTrue(result.success)
        product.refresh_from_db()
        variant.refresh_from_db()
        self.assertEqual(product.name_ru, 'Updated Name')
        self.assertEqual(variant.stock_quantity, 8)
        self.assertEqual(variant.variant_price, Decimal('105.00'))
        movement = StockMovement.objects.get(variant=variant)
        self.assertEqual(movement.quantity, 6)

    def test_process_import_continues_after_row_errors(self):
        content = (
            'product_name,category_slug,price,sku,stock_quantity\n'
            'Valid Product,shoes,100.00,VALID-SKU,4\n'
            'Invalid Product,missing,100.00,INVALID-SKU,2\n'
        )
        job = self.make_job(content)

        ProductImportService.process_import(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED_WITH_ERRORS)
        self.assertEqual(job.total_count, 2)
        self.assertEqual(job.success_count, 1)
        self.assertEqual(job.failed_count, 1)
        self.assertTrue(ProductVariant.objects.filter(sku='VALID-SKU').exists())
        self.assertFalse(ProductVariant.objects.filter(sku='INVALID-SKU').exists())
        self.assertEqual(ImportJobError.objects.filter(import_job=job).count(), 1)
        self.assertIsInstance(job.error_report, dict)
        self.assertEqual(job.error_report['format'], 'csv')
        self.assertNotIn('url', job.error_report)
        with job.file.storage.open(job.error_report['file'], 'rb') as report_file:
            report = report_file.read().decode('utf-8-sig')
        rows = list(csv.DictReader(io.StringIO(report)))
        self.assertEqual(rows[0]['row_number'], '3')
        self.assertEqual(rows[0]['error_message'], 'Ошибка валидации строки.')
        self.assertEqual(rows[0]['sku'], 'INVALID-SKU')

    def test_process_import_without_errors_does_not_generate_error_report(self):
        content = (
            'product_name,category_slug,price,sku,stock_quantity\n'
            'Valid Product,shoes,100.00,VALID-SKU,4\n'
        )
        job = self.make_job(content)

        ProductImportService.process_import(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertIsNone(job.error_report)

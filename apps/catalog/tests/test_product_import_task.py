import shutil
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.catalog.models import (
    Category, ImportJob, ImportJobError, ProductVariant, StockMovement,
)
from apps.catalog.tasks import process_product_import


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ProductImportTaskTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.user = User.objects.create_user(
            email='import-task-manager@example.com',
            role=User.Role.MANAGER,
        )
        self.category = Category.objects.create(name='Shoes', slug='shoes')

    def make_job(self, content, status=ImportJob.Status.PENDING):
        return ImportJob.objects.create(
            file=SimpleUploadedFile(
                'products.csv',
                content.encode('utf-8'),
                content_type='text/csv',
            ),
            created_by=self.user,
            status=status,
        )

    def valid_csv(self, sku='TASK-SKU', stock_quantity='4'):
        return (
            'product_name,category_slug,price,sku,stock_quantity\n'
            f'Task Product,shoes,100.00,{sku},{stock_quantity}\n'
        )

    def test_task_marks_pending_job_processing_before_service_runs(self):
        job = self.make_job(self.valid_csv())

        with patch('apps.catalog.tasks.ProductImportService.process_import') as process_import:
            process_product_import.apply(args=(job.id,))

        process_import.assert_called_once()
        service_job = process_import.call_args.args[0]
        service_job.refresh_from_db()
        self.assertEqual(service_job.status, ImportJob.Status.PROCESSING)
        self.assertIsNotNone(service_job.started_at)

    def test_successful_import_marks_completed(self):
        job = self.make_job(self.valid_csv())

        result = process_product_import.apply(args=(job.id,))

        self.assertEqual(result.result['status'], 'processed')
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)
        self.assertEqual(job.total_count, 1)
        self.assertEqual(job.success_count, 1)
        self.assertEqual(job.failed_count, 0)
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.finished_at)
        variant = ProductVariant.objects.get(sku='TASK-SKU')
        self.assertEqual(variant.stock_quantity, 4)
        self.assertEqual(StockMovement.objects.get(variant=variant).quantity, 4)

    def test_partial_errors_mark_completed_with_errors_and_set_counters(self):
        job = self.make_job(
            'product_name,category_slug,price,sku,stock_quantity\n'
            'Valid Product,shoes,100.00,VALID-TASK-SKU,3\n'
            'Invalid Product,missing,100.00,INVALID-TASK-SKU,2\n'
        )

        process_product_import.apply(args=(job.id,))

        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED_WITH_ERRORS)
        self.assertEqual(job.total_count, 2)
        self.assertEqual(job.success_count, 1)
        self.assertEqual(job.failed_count, 1)
        self.assertEqual(ImportJobError.objects.filter(import_job=job).count(), 1)
        self.assertTrue(ProductVariant.objects.filter(sku='VALID-TASK-SKU').exists())
        self.assertFalse(ProductVariant.objects.filter(sku='INVALID-TASK-SKU').exists())

    def test_fatal_error_marks_failed(self):
        job = self.make_job('product_name,price,sku\nFatal Product,100.00,FATAL-SKU\n')

        result = process_product_import.apply(args=(job.id,))

        self.assertEqual(result.result['status'], 'failed')
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertIn('Отсутствуют обязательные колонки', job.error_message)
        self.assertIsNotNone(job.finished_at)

    def test_duplicate_task_call_does_not_reprocess_completed_job(self):
        job = self.make_job(self.valid_csv(stock_quantity='5'))

        process_product_import.apply(args=(job.id,))
        first_movement_count = StockMovement.objects.count()

        result = process_product_import.apply(args=(job.id,))

        self.assertEqual(result.result['status'], 'skipped')
        self.assertEqual(StockMovement.objects.count(), first_movement_count)
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.COMPLETED)

    def test_missing_job_exits_safely(self):
        result = process_product_import.apply(args=(999999,))

        self.assertEqual(result.result['status'], 'missing')

    def test_existing_sku_is_updated_by_task(self):
        job = self.make_job(self.valid_csv(stock_quantity='2'))
        process_product_import.apply(args=(job.id,))
        variant = ProductVariant.objects.get(sku='TASK-SKU')
        self.assertEqual(variant.product.price, Decimal('100.00'))

        retry_job = self.make_job(
            'product_name,category_slug,price,sku,stock_quantity\n'
            'Updated Task Product,shoes,120.00,TASK-SKU,7\n'
        )
        process_product_import.apply(args=(retry_job.id,))

        variant.refresh_from_db()
        self.assertEqual(variant.product.name, 'Updated Task Product')
        self.assertEqual(variant.product.price, Decimal('120.00'))
        self.assertEqual(variant.stock_quantity, 7)

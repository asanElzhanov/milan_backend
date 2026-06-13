import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.models import ImportJob, ImportJobError


class ProductImportApiTests(APITestCase):
    imports_url = '/api/v1/catalog/imports/products/'

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.manager = User.objects.create_user(
            email='manager-import-api@example.com',
            password='secret123',
            role=User.Role.MANAGER,
        )
        self.customer = User.objects.create_user(
            email='customer-import-api@example.com',
            password='secret123',
        )

    def csv_file(self, name='products.csv', content=None, content_type='text/csv'):
        if content is None:
            content = (
                'product_name,category_slug,price,sku,stock_quantity\n'
                'API Product,shoes,100.00,API-SKU,3\n'
            )
        return SimpleUploadedFile(
            name,
            content.encode('utf-8'),
            content_type=content_type,
        )

    def authenticate_manager(self):
        self.client.force_authenticate(self.manager)

    def response_items(self, response):
        return response.data['results'] if isinstance(response.data, dict) else response.data

    def detail_url(self, import_job):
        return f'{self.imports_url}{import_job.id}/'

    def errors_url(self, import_job):
        return f'{self.imports_url}{import_job.id}/errors/'

    def make_job(self, **kwargs):
        defaults = {
            'file': self.csv_file(),
            'created_by': self.manager,
        }
        defaults.update(kwargs)
        return ImportJob.objects.create(**defaults)

    def test_manager_can_upload_csv_and_task_is_scheduled(self):
        self.authenticate_manager()

        with patch('apps.catalog.views.schedule_product_import') as schedule_import:
            response = self.client.post(
                self.imports_url,
                {'file': self.csv_file()},
                format='multipart',
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        import_job = ImportJob.objects.get()
        self.assertEqual(import_job.created_by, self.manager)
        self.assertEqual(import_job.status, ImportJob.Status.PENDING)
        schedule_import.assert_called_once_with(import_job.id)
        self.assertEqual(response.data['id'], import_job.id)
        self.assertEqual(response.data['status'], ImportJob.Status.PENDING)
        self.assertEqual(response.data['created_by']['email'], self.manager.email)

    def test_upload_does_not_process_csv_synchronously(self):
        self.authenticate_manager()

        with patch('apps.catalog.views.schedule_product_import'):
            response = self.client.post(
                self.imports_url,
                {'file': self.csv_file()},
                format='multipart',
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        import_job = ImportJob.objects.get()
        self.assertEqual(import_job.total_count, 0)
        self.assertEqual(import_job.success_count, 0)
        self.assertEqual(import_job.failed_count, 0)
        self.assertFalse(import_job.started_at)

    def test_customer_cannot_access_imports(self):
        import_job = self.make_job()
        self.client.force_authenticate(self.customer)

        list_response = self.client.get(self.imports_url)
        upload_response = self.client.post(
            self.imports_url,
            {'file': self.csv_file()},
            format='multipart',
        )
        detail_response = self.client.get(self.detail_url(import_job))
        errors_response = self.client.get(self.errors_url(import_job))

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(upload_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detail_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(errors_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_upload_requires_file(self):
        self.authenticate_manager()

        response = self.client.post(self.imports_url, {}, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)

    def test_invalid_file_extension_is_rejected(self):
        self.authenticate_manager()

        response = self.client.post(
            self.imports_url,
            {'file': self.csv_file(name='products.txt', content_type='text/plain')},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)
        self.assertFalse(ImportJob.objects.exists())

    def test_invalid_content_type_is_rejected(self):
        self.authenticate_manager()

        response = self.client.post(
            self.imports_url,
            {'file': self.csv_file(name='products.csv', content_type='image/png')},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('file', response.data)
        self.assertFalse(ImportJob.objects.exists())

    def test_import_history_is_listed_and_filterable(self):
        self.authenticate_manager()
        completed = self.make_job(status=ImportJob.Status.COMPLETED)
        self.make_job(status=ImportJob.Status.FAILED)

        response = self.client.get(self.imports_url, {'status': ImportJob.Status.COMPLETED})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        items = self.response_items(response)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(items[0]['id'], completed.id)
        self.assertEqual(items[0]['status'], ImportJob.Status.COMPLETED)

    def test_import_history_filters_by_created_by_and_dates(self):
        self.authenticate_manager()
        other_manager = User.objects.create_user(
            email='other-import-manager@example.com',
            role=User.Role.MANAGER,
        )
        target = self.make_job(created_by=self.manager)
        self.make_job(created_by=other_manager)
        date_from = timezone.localtime(target.created_at).isoformat()

        response = self.client.get(
            self.imports_url,
            {'created_by': str(self.manager.id), 'date_from': date_from},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(self.response_items(response)[0]['id'], target.id)

    def test_import_detail_is_returned(self):
        self.authenticate_manager()
        import_job = self.make_job(
            status=ImportJob.Status.COMPLETED_WITH_ERRORS,
            total_count=2,
            success_count=1,
            failed_count=1,
            error_report=[{'row_number': 3, 'error_message': 'Invalid row'}],
        )

        response = self.client.get(self.detail_url(import_job))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], import_job.id)
        self.assertEqual(response.data['total_count'], 2)
        self.assertEqual(response.data['error_report'][0]['row_number'], 3)

    def test_errors_endpoint_returns_row_errors(self):
        self.authenticate_manager()
        import_job = self.make_job(status=ImportJob.Status.COMPLETED_WITH_ERRORS)
        ImportJobError.objects.create(
            import_job=import_job,
            row_number=2,
            row_data={'sku': 'BAD-SKU'},
            error_message='Ошибка валидации строки.',
            field_errors={'price': 'invalid'},
        )

        response = self.client.get(self.errors_url(import_job))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        item = self.response_items(response)[0]
        self.assertEqual(item['row_number'], 2)
        self.assertEqual(item['row_data']['sku'], 'BAD-SKU')
        self.assertEqual(item['field_errors']['price'], 'invalid')

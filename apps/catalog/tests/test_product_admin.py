from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import (
    Brand, Category, Color, ImportJob, ImportJobError,
    Product, ProductVariant, Size, StockMovement,
)


class ProductAdminTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='secret123',
        )
        self.client.force_login(self.admin_user)
        self.category = Category.objects.create(name_ru='Shoes', slug='shoes')
        self.brand = Brand.objects.create(name_ru='Nike', slug='nike')
        self.color = Color.objects.create(name_ru='Black', slug='black', hex_code='#000000')
        self.size = Size.objects.create(value='42', size_type=Size.SizeType.SHOES)
        self.product = Product.objects.create(
            sku='SKU-ADMIN',
            name_ru='Admin Product',
            slug='admin-product',
            category=self.category,
            brand=self.brand,
            price=Decimal('100.00'),
            old_price=Decimal('120.00'),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color=self.color,
            size=self.size,
            sku='VAR-ADMIN-42-BLACK',
            stock_quantity=3,
        )

    def test_product_changelist_opens(self):
        response = self.client.get(reverse('admin:catalog_product_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Product')

    def test_product_change_page_opens_with_inlines(self):
        response = self.client.get(reverse('admin:catalog_product_change', args=[self.product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAR-ADMIN-42-BLACK')
        self.assertContains(response, 'id_images-TOTAL_FORMS')
        self.assertContains(response, 'id_media-TOTAL_FORMS')

    def test_product_admin_searches_by_variant_sku(self):
        response = self.client.get(
            reverse('admin:catalog_product_changelist'),
            {'q': self.variant.sku},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Product')

    def test_product_admin_filters_by_stock(self):
        response = self.client.get(
            reverse('admin:catalog_product_changelist'),
            {'in_stock': 'yes'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Product')

    def test_product_variant_admin_opens_with_read_only_stock(self):
        response = self.client.get(reverse('admin:catalog_productvariant_change', args=[self.variant.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAR-ADMIN-42-BLACK')
        self.assertContains(response, 'Остаток')

    def test_stock_movement_admin_is_read_only(self):
        movement = StockMovement.objects.create(
            variant=self.variant,
            quantity=1,
            operation_type=StockMovement.OperationType.INCOME,
            user=self.admin_user,
            comment='Readonly history',
        )

        response = self.client.post(
            reverse('admin:catalog_stockmovement_change', args=[movement.pk]),
            {
                'variant': self.variant.pk,
                'quantity': 99,
                'operation_type': StockMovement.OperationType.SALE,
                'comment': 'Changed',
            },
        )

        self.assertEqual(response.status_code, 403)
        movement.refresh_from_db()
        self.assertEqual(movement.quantity, 1)
        self.assertEqual(movement.operation_type, StockMovement.OperationType.INCOME)
        self.assertEqual(movement.comment, 'Readonly history')

    def test_import_job_changelist_opens(self):
        import_job = ImportJob.objects.create(
            file='catalog/imports/products.csv',
            created_by=self.admin_user,
            status=ImportJob.Status.COMPLETED_WITH_ERRORS,
            total_count=2,
            success_count=1,
            failed_count=1,
            error_message='Import finished with errors',
        )

        response = self.client.get(reverse('admin:catalog_importjob_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(import_job.id))
        self.assertContains(response, 'completed_with_errors')
        self.assertContains(response, self.admin_user.email)

    def test_import_job_admin_searches_by_error_message(self):
        import_job = ImportJob.objects.create(
            file='catalog/imports/products.csv',
            created_by=self.admin_user,
            error_message='Fatal CSV header error',
        )

        response = self.client.get(
            reverse('admin:catalog_importjob_changelist'),
            {'q': 'Fatal CSV header'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(import_job.id))

    def test_import_job_change_page_has_readonly_status_and_counts(self):
        import_job = ImportJob.objects.create(
            file='catalog/imports/products.csv',
            created_by=self.admin_user,
            status=ImportJob.Status.COMPLETED,
            total_count=1,
            success_count=1,
        )

        response = self.client.get(reverse('admin:catalog_importjob_change', args=[import_job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Статус')
        self.assertContains(response, 'completed')
        self.assertNotContains(response, 'name_ru="status"')
        self.assertNotContains(response, 'name_ru="total_count"')

    def test_import_job_error_admin_opens_and_is_read_only(self):
        import_job = ImportJob.objects.create(
            file='catalog/imports/products.csv',
            created_by=self.admin_user,
            status=ImportJob.Status.COMPLETED_WITH_ERRORS,
            failed_count=1,
        )
        error = ImportJobError.objects.create(
            import_job=import_job,
            row_number=2,
            row_data={'sku': 'BAD-SKU'},
            error_message='Invalid price',
            field_errors={'price': 'invalid'},
        )

        changelist_response = self.client.get(reverse('admin:catalog_importjoberror_changelist'))
        change_response = self.client.get(reverse('admin:catalog_importjoberror_change', args=[error.pk]))
        post_response = self.client.post(
            reverse('admin:catalog_importjoberror_change', args=[error.pk]),
            {
                'import_job': import_job.pk,
                'row_number': 99,
                'error_message': 'Changed',
                'row_data': '{}',
                'field_errors': '{}',
            },
        )

        self.assertEqual(changelist_response.status_code, 200)
        self.assertContains(changelist_response, 'Invalid price')
        self.assertEqual(change_response.status_code, 200)
        self.assertContains(change_response, 'BAD-SKU')
        self.assertNotContains(change_response, 'name_ru="row_number"')
        self.assertEqual(post_response.status_code, 403)
        error.refresh_from_db()
        self.assertEqual(error.row_number, 2)
        self.assertEqual(error.error_message, 'Invalid price')

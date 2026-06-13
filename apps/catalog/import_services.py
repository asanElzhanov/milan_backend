import csv
import io
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    Brand, Category, Color, ImportJob, ImportJobError,
    Product, ProductVariant, Size,
)
from .services import InvalidStockQuantityError, StockService


logger = logging.getLogger(__name__)


class ProductImportError(Exception):
    pass


@dataclass
class RowValidationResult:
    valid: bool
    data: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)


@dataclass
class RowProcessResult:
    success: bool
    error_message: str = ''
    field_errors: dict = field(default_factory=dict)


class ProductImportService:
    required_columns = {
        'product_name',
        'category_slug',
        'price',
        'sku',
        'stock_quantity',
    }
    allowed_columns = required_columns | {
        'product_sku',
        'product_slug',
        'description',
        'brand_slug',
        'old_price',
        'is_new',
        'is_active',
        'seo_title',
        'seo_description',
        'size_value',
        'size_type',
        'color_slug',
        'variant_price',
        'variant_is_active',
    }
    true_values = {'true', '1', 'yes', 'y'}
    false_values = {'false', '0', 'no', 'n'}

    @classmethod
    def validate_headers(cls, headers):
        normalized_headers = {
            cls._normalize_header(header)
            for header in headers
            if cls._normalize_header(header)
        }
        missing = sorted(cls.required_columns - normalized_headers)
        unknown = sorted(normalized_headers - cls.allowed_columns)
        return {
            'missing': missing,
            'unknown': unknown,
        }

    @classmethod
    def parse_bool(cls, value):
        value = cls._normalize_value(value)
        if value is None:
            return None
        lowered = value.lower()
        if lowered in cls.true_values:
            return True
        if lowered in cls.false_values:
            return False
        raise ProductImportError('Значение должно быть true/false, 1/0 или yes/no.')

    @classmethod
    def parse_decimal(cls, value, field_name):
        value = cls._normalize_value(value)
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ProductImportError(f'{field_name}: укажите корректное число.') from exc
        if parsed < 0:
            raise ProductImportError(f'{field_name}: значение не может быть отрицательным.')
        return parsed

    @classmethod
    def parse_int(cls, value, field_name):
        value = cls._normalize_value(value)
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ProductImportError(f'{field_name}: укажите целое число.') from exc
        if parsed < 0:
            raise ProductImportError(f'{field_name}: значение не может быть отрицательным.')
        return parsed

    @classmethod
    def validate_row(cls, row, row_number):
        normalized_row = cls._normalize_row(row)
        errors = {}
        data = {}

        for column in cls.required_columns:
            if normalized_row.get(column) is None:
                errors[column] = 'Обязательное поле.'

        data['product_name'] = normalized_row.get('product_name')
        data['product_sku'] = normalized_row.get('product_sku')
        data['product_slug'] = normalized_row.get('product_slug')
        data['description'] = normalized_row.get('description') or ''
        data['seo_title'] = normalized_row.get('seo_title') or ''
        data['seo_description'] = normalized_row.get('seo_description') or ''
        data['sku'] = normalized_row.get('sku')

        for field_name in ('price', 'old_price', 'variant_price'):
            try:
                data[field_name] = cls.parse_decimal(normalized_row.get(field_name), field_name)
            except ProductImportError as exc:
                errors[field_name] = str(exc)

        try:
            data['stock_quantity'] = cls.parse_int(
                normalized_row.get('stock_quantity'),
                'stock_quantity',
            )
        except ProductImportError as exc:
            errors['stock_quantity'] = str(exc)

        for source, target in (
            ('is_new', 'is_new'),
            ('is_active', 'is_active'),
            ('variant_is_active', 'variant_is_active'),
        ):
            try:
                data[target] = cls.parse_bool(normalized_row.get(source))
            except ProductImportError as exc:
                errors[source] = str(exc)

        if data.get('is_new') is None:
            data['is_new'] = False
        if data.get('is_active') is None:
            data['is_active'] = True
        if data.get('variant_is_active') is None:
            data['variant_is_active'] = True

        if data.get('old_price') is not None and data.get('price') is not None:
            if data['old_price'] < data['price']:
                errors['old_price'] = 'Старая цена не может быть меньше текущей цены.'

        category_slug = normalized_row.get('category_slug')
        data['category'] = cls._get_required_object(
            Category,
            {'slug': category_slug},
            'category_slug',
            errors,
        )

        brand_slug = normalized_row.get('brand_slug')
        data['brand'] = cls._get_optional_object(
            Brand,
            {'slug': brand_slug},
            'brand_slug',
            errors,
        )

        color_slug = normalized_row.get('color_slug')
        data['color'] = cls._get_optional_object(
            Color,
            {'slug': color_slug},
            'color_slug',
            errors,
        )

        size_value = normalized_row.get('size_value')
        size_type = normalized_row.get('size_type')
        data['size'] = None
        if size_value or size_type:
            if not size_value:
                errors['size_value'] = 'Укажите size_value вместе с size_type.'
            if not size_type:
                errors['size_type'] = 'Укажите size_type вместе с size_value.'
            if size_value and size_type:
                size = Size.objects.filter(value=size_value, size_type=size_type).first()
                if size is None:
                    errors['size'] = 'Размер не найден.'
                else:
                    data['size'] = size

        return RowValidationResult(valid=not errors, data=data, errors=errors)

    @classmethod
    def process_row(cls, row, row_number, import_job):
        validation = cls.validate_row(row, row_number)
        if not validation.valid:
            cls._record_row_error(import_job, row_number, row, validation.errors)
            return RowProcessResult(
                success=False,
                error_message='Ошибка валидации строки.',
                field_errors=validation.errors,
            )

        try:
            with transaction.atomic():
                product = cls._create_or_update_product(validation.data)
                variant = cls._create_or_update_variant(product, validation.data)
                cls._sync_stock(variant, validation.data['stock_quantity'], import_job)
        except (ValidationError, IntegrityError, ProductImportError) as exc:
            field_errors = cls._extract_validation_errors(exc)
            cls._record_row_error(import_job, row_number, row, field_errors, str(exc))
            return RowProcessResult(
                success=False,
                error_message=str(exc),
                field_errors=field_errors,
            )

        return RowProcessResult(success=True)

    @classmethod
    def process_import(cls, import_job):
        ImportJobError.objects.filter(import_job=import_job).delete()
        import_job.status = ImportJob.Status.PROCESSING
        import_job.started_at = timezone.now()
        import_job.error_message = ''
        import_job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])

        try:
            with cls.open_csv(import_job.file) as rows:
                header_result = cls.validate_headers(rows.fieldnames or [])
                if header_result['missing']:
                    raise ProductImportError(
                        'Отсутствуют обязательные колонки: '
                        + ', '.join(header_result['missing'])
                    )

                success_count = 0
                failed_count = 0
                for row_number, row in enumerate(rows, start=2):
                    result = cls.process_row(row, row_number, import_job)
                    if result.success:
                        success_count += 1
                    else:
                        failed_count += 1

            import_job.total_count = success_count + failed_count
            import_job.success_count = success_count
            import_job.failed_count = failed_count
            import_job.error_report = cls._build_error_report(import_job) if failed_count else None
            import_job.status = (
                ImportJob.Status.COMPLETED_WITH_ERRORS
                if failed_count
                else ImportJob.Status.COMPLETED
            )
            import_job.finished_at = timezone.now()
            import_job.save(update_fields=[
                'total_count', 'success_count', 'failed_count', 'error_report',
                'status', 'finished_at', 'updated_at',
            ])
        except Exception as exc:
            import_job.status = ImportJob.Status.FAILED
            import_job.error_message = str(exc)[:500]
            import_job.finished_at = timezone.now()
            import_job.save(update_fields=[
                'status', 'error_message', 'finished_at', 'updated_at',
            ])
            raise

        return import_job

    @classmethod
    @contextmanager
    def open_csv(cls, file_obj):
        file_obj.open('rb')
        text_file = io.TextIOWrapper(file_obj.file, encoding='utf-8-sig', newline='')
        try:
            yield csv.DictReader(text_file)
        except UnicodeDecodeError as exc:
            raise ProductImportError('CSV файл должен быть в UTF-8.') from exc
        finally:
            text_file.close()
            file_obj.close()

    @classmethod
    def _build_error_report(cls, import_job):
        try:
            return cls.generate_error_report(import_job)
        except Exception:
            logger.exception('Failed to generate import error report for job %s', import_job.pk)
            return None

    @classmethod
    def generate_error_report(cls, import_job):
        errors = ImportJobError.objects.filter(
            import_job=import_job,
        ).order_by('row_number', 'id')
        if not errors.exists():
            return None

        row_keys = []
        seen_keys = set()
        for error in errors.iterator():
            for key in error.row_data.keys():
                if key not in seen_keys:
                    seen_keys.add(key)
                    row_keys.append(key)

        fieldnames = ['row_number', 'error_message', 'field_errors'] + row_keys
        tmp_path = None
        path = f'catalog/imports/error_reports/import-{import_job.pk}-errors.csv'
        storage = import_job.file.storage
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                newline='',
                encoding='utf-8-sig',
                delete=False,
            ) as tmp:
                tmp_path = tmp.name
                writer = csv.DictWriter(tmp, fieldnames=fieldnames)
                writer.writeheader()
                for error in errors.iterator():
                    row = {
                        'row_number': error.row_number,
                        'error_message': error.error_message,
                        'field_errors': json.dumps(error.field_errors, ensure_ascii=False),
                    }
                    row.update({
                        key: error.row_data.get(key, '')
                        for key in row_keys
                    })
                    writer.writerow(row)

            with open(tmp_path, 'rb') as report_file:
                saved_path = storage.save(path, File(report_file, name=path))
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.exception('Failed to delete temporary import report %s', tmp_path)

        report = {
            'file': saved_path,
            'format': 'csv',
        }
        try:
            report['url'] = storage.url(saved_path)
        except Exception:
            logger.exception('Failed to build import error report URL for job %s', import_job.pk)
        return report

    @classmethod
    def _create_or_update_product(cls, data):
        variant = ProductVariant.objects.select_related('product').filter(
            sku=data['sku'],
        ).first()
        slug = data.get('product_slug') or slugify(data['product_name'], allow_unicode=True)
        product = None
        if data.get('product_slug'):
            product = Product.objects.filter(slug=data['product_slug']).first()
        if product is None and variant is not None:
            product = variant.product
        if product is None:
            product = Product.objects.filter(slug=slug).first()

        product_sku = data.get('product_sku') or data['sku']
        if product is None:
            product = Product(sku=product_sku, slug=slug)
        elif data.get('product_sku'):
            product.sku = data['product_sku']

        product.name = data['product_name']
        product.category = data['category']
        product.brand = data['brand']
        product.price = data['price']
        product.old_price = data['old_price']
        product.description = data['description']
        product.is_new = data['is_new']
        product.is_active = data['is_active']
        product.seo_title = data['seo_title']
        product.seo_description = data['seo_description']
        product.full_clean()
        product.save()
        return product

    @classmethod
    def _create_or_update_variant(cls, product, data):
        variant = ProductVariant.objects.filter(sku=data['sku']).first()
        if variant is None:
            variant = ProductVariant(product=product, sku=data['sku'])
        elif variant.product_id != product.id:
            raise ProductImportError('SKU уже принадлежит другому товару.')

        variant.color = data['color']
        variant.size = data['size']
        variant.variant_price = data['variant_price']
        variant.is_active = data['variant_is_active']
        if variant.pk is None:
            variant.stock_quantity = 0
        variant.full_clean()
        variant.save()
        return variant

    @classmethod
    def _sync_stock(cls, variant, stock_quantity, import_job):
        if variant.stock_quantity == stock_quantity:
            return
        try:
            StockService.manual_adjustment(
                variant,
                stock_quantity,
                user=import_job.created_by,
                comment=f'Product CSV import #{import_job.pk}',
            )
        except InvalidStockQuantityError:
            return

    @classmethod
    def _record_row_error(cls, import_job, row_number, row, field_errors, error_message=''):
        ImportJobError.objects.create(
            import_job=import_job,
            row_number=row_number,
            row_data=cls._normalize_row(row),
            error_message=error_message or 'Ошибка валидации строки.',
            field_errors=field_errors,
        )

    @classmethod
    def _get_required_object(cls, model, lookup, field_name, errors):
        value = next(iter(lookup.values()))
        if value is None:
            return None
        obj = model.objects.filter(**lookup).first()
        if obj is None:
            errors[field_name] = 'Объект не найден.'
        return obj

    @classmethod
    def _get_optional_object(cls, model, lookup, field_name, errors):
        value = next(iter(lookup.values()))
        if value is None:
            return None
        obj = model.objects.filter(**lookup).first()
        if obj is None:
            errors[field_name] = 'Объект не найден.'
        return obj

    @staticmethod
    def _extract_validation_errors(exc):
        if hasattr(exc, 'message_dict'):
            return exc.message_dict
        return {'non_field_errors': [str(exc)]}

    @classmethod
    def _normalize_row(cls, row):
        return {
            cls._normalize_header(key): cls._normalize_value(value)
            for key, value in row.items()
            if cls._normalize_header(key)
        }

    @staticmethod
    def _normalize_header(header):
        return str(header or '').strip().lower()

    @staticmethod
    def _normalize_value(value):
        if value is None:
            return None
        value = str(value).strip()
        return value if value != '' else None

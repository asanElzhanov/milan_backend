import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .import_services import ProductImportService
from .models import ImportJob


logger = logging.getLogger(__name__)


def schedule_product_import(import_job_id):
    transaction.on_commit(lambda: process_product_import.delay(import_job_id))


@shared_task(bind=True, max_retries=0, name='catalog.process_product_import')
def process_product_import(self, import_job_id):
    try:
        with transaction.atomic():
            import_job = ImportJob.objects.select_for_update().get(pk=import_job_id)
            if import_job.status != ImportJob.Status.PENDING:
                logger.info(
                    'Skipping product import job %s with status %s',
                    import_job_id,
                    import_job.status,
                )
                return {
                    'status': 'skipped',
                    'import_job_id': import_job_id,
                    'import_job_status': import_job.status,
                }

            import_job.status = ImportJob.Status.PROCESSING
            import_job.started_at = timezone.now()
            import_job.error_message = ''
            import_job.save(update_fields=['status', 'started_at', 'error_message', 'updated_at'])
    except ImportJob.DoesNotExist:
        logger.warning('Product import job %s does not exist', import_job_id)
        return {
            'status': 'missing',
            'import_job_id': import_job_id,
        }

    try:
        ProductImportService.process_import(import_job)
    except Exception:
        logger.exception('Product import job %s failed', import_job_id)
        import_job.refresh_from_db()
        return {
            'status': 'failed',
            'import_job_id': import_job_id,
            'import_job_status': import_job.status,
        }

    import_job.refresh_from_db()
    return {
        'status': 'processed',
        'import_job_id': import_job_id,
        'import_job_status': import_job.status,
        'total_count': import_job.total_count,
        'success_count': import_job.success_count,
        'failed_count': import_job.failed_count,
    }

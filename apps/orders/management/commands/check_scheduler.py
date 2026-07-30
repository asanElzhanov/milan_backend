from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.tasks import cancel_unpaid_order


class Command(BaseCommand):
    help = 'Показать неоплаченные заказы и запланированные авто-отмены (Celery ETA).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cancel',
            type=int,
            metavar='ORDER_ID',
            help='Запустить задачу отмены для конкретного заказа прямо сейчас.',
        )

    def handle(self, *args, **options):
        timeout_minutes = getattr(settings, 'ORDER_PAYMENT_TIMEOUT_MINUTES', 30)
        self.stdout.write(self.style.SUCCESS('=== Авто-отмена заказов ===\n'))
        self.stdout.write(f'Таймаут оплаты: {timeout_minutes} мин')
        self.stdout.write(
            'Задача отмены планируется в момент создания заказа '
            '(Celery apply_async с countdown).\n'
        )

        # Неоплаченные заказы, для которых должна быть запланирована отмена.
        pending = Order.objects.filter(
            status__in=[Order.Status.NEW, Order.Status.WAITING_PAYMENT],
            payment_status__in=[Order.PaymentStatus.UNPAID, Order.PaymentStatus.WAITING],
        ).order_by('created_at')

        self.stdout.write(f'Ожидают оплаты: {pending.count()}\n')
        now = timezone.now()
        for order in pending[:50]:
            age_min = (now - order.created_at).total_seconds() / 60
            cancel_at = order.created_at + timedelta(minutes=timeout_minutes)
            left_min = (cancel_at - now).total_seconds() / 60
            if left_min > 0:
                when = f'отмена через ~{left_min:.0f} мин'
            else:
                when = self.style.WARNING('просрочен — задача должна была сработать')
            self.stdout.write(
                f'  {order.order_number}: создан {age_min:.0f} мин назад — {when}'
            )

        # Запланированные ETA-задачи в Celery (если воркер доступен).
        self.stdout.write('\n=== Запланированные задачи в Celery ===')
        try:
            from config.celery import app as celery_app

            inspect = celery_app.control.inspect()
            scheduled = inspect.scheduled() or {}
            if not scheduled:
                self.stdout.write(
                    self.style.WARNING(
                        'Воркеры не отвечают или нет запланированных задач.\n'
                        'Убедитесь, что запущен: celery -A config worker -l info'
                    )
                )
            for worker, jobs in scheduled.items():
                cancel_jobs = [
                    j for j in jobs
                    if j.get('request', {}).get('name') == 'orders.cancel_unpaid_order'
                ]
                self.stdout.write(f'  {worker}: {len(cancel_jobs)} задач отмены в очереди ETA')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Не удалось опросить Celery: {e}'))

        if options['cancel']:
            order_id = options['cancel']
            self.stdout.write(f'\n=== Запуск отмены для заказа #{order_id} ===')
            result = cancel_unpaid_order(order_id)
            self.stdout.write(self.style.SUCCESS(f'Результат: {result}'))

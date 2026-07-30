from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.orders.models import Order
from apps.orders.tasks import cancel_expired_orders
from django.conf import settings


class Command(BaseCommand):
    help = 'Проверить статус scheduler и протестировать отмену заказов'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help='Протестировать отмену с тестовым заказом',
        )
        parser.add_argument(
            '--run-now',
            action='store_true',
            help='Запустить проверку просроченных заказов прямо сейчас',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Статус Scheduler ===\n'))

        # Проверка конфигурации
        timeout_minutes = getattr(settings, 'ORDER_PAYMENT_TIMEOUT_MINUTES', 30)
        check_minutes = getattr(settings, 'ORDER_EXPIRY_CHECK_MINUTES', 5)

        self.stdout.write(f'ORDER_PAYMENT_TIMEOUT_MINUTES: {timeout_minutes} мин')
        self.stdout.write(f'ORDER_EXPIRY_CHECK_MINUTES: {check_minutes} мин\n')

        # Проверка scheduler'а
        try:
            from apps.orders.scheduler import scheduler

            if scheduler and scheduler.running:
                self.stdout.write(self.style.SUCCESS('✓ Scheduler активен'))
                jobs = scheduler.get_jobs()
                self.stdout.write(f'  Активных задач: {len(jobs)}')
                for job in jobs:
                    self.stdout.write(f'  - {job.name} (каждые {job.trigger})')
            else:
                self.stdout.write(self.style.WARNING('✗ Scheduler не запущен'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Ошибка scheduler: {e}'))

        # Статистика заказов
        self.stdout.write('\n=== Статистика заказов ===\n')
        new_orders = Order.objects.filter(status='new', payment_status='unpaid').count()
        waiting_orders = Order.objects.filter(
            status='waiting_payment',
            payment_status__in=['unpaid', 'waiting']
        ).count()

        self.stdout.write(f'Новые заказы (NEW): {new_orders}')
        self.stdout.write(f'Ожидают оплаты (WAITING_PAYMENT): {waiting_orders}')

        # Просроченные заказы
        cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
        expired = Order.objects.filter(
            status__in=['new', 'waiting_payment'],
            payment_status__in=['unpaid', 'waiting'],
            created_at__lt=cutoff,
        ).count()
        self.stdout.write(f'Просроченные (готовы к отмене): {expired}\n')

        # Тестирование
        if options['test']:
            self.stdout.write(self.style.SUCCESS('=== Тест отмены ===\n'))
            self.test_cancellation()

        # Запуск прямо сейчас
        if options['run_now']:
            self.stdout.write(self.style.SUCCESS('=== Запуск проверки сейчас ===\n'))
            try:
                result = cancel_expired_orders()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Проверено: {result['checked']}, Отменено: {result['cancelled']}"
                    )
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'✗ Ошибка: {e}'))

    def test_cancellation(self):
        """Создать тестовый заказ и проверить его отмену"""
        from apps.orders.models import Order, Cart, CartItem
        from apps.catalog.models import ProductVariant
        from apps.orders.services import CheckoutService
        from decimal import Decimal

        # Найти или создать товар
        variant = ProductVariant.objects.filter(stock_quantity__gt=0).first()
        if not variant:
            self.stdout.write(self.style.WARNING('✗ Нет активных товаров для теста'))
            return

        # Создать тестовый заказ
        cart = Cart.objects.create(user=None, is_active=True)
        CartItem.objects.create(cart=cart, variant=variant, quantity=1)

        try:
            order = CheckoutService.checkout(
                cart=cart,
                customer_name='Test Customer',
                phone='+77011234567',
                email='test@example.com',
                city='Almaty',
                delivery_address='Test Address',
                delivery_method=1,  # Предположим, что есть способ доставки с ID 1
            )

            self.stdout.write(f'Создан заказ: {order.order_number}')
            self.stdout.write(f'  Статус: {order.status}')
            self.stdout.write(f'  Платёж: {order.payment_status}')
            self.stdout.write(f'  Создан: {order.created_at}')

            # Отодвинуть время на 31 минуту назад
            Order.objects.filter(pk=order.pk).update(
                created_at=timezone.now() - timedelta(minutes=31)
            )

            self.stdout.write('\nЗаказ отодвинут на 31 минуту назад')

            # Запустить отмену
            result = cancel_expired_orders()

            # Проверить результат
            order.refresh_from_db()
            self.stdout.write(f'\nПосле проверки:')
            self.stdout.write(f'  Статус: {order.status}')
            self.stdout.write(f'  Платёж: {order.payment_status}')

            if order.status == 'cancelled' and order.payment_status == 'expired':
                self.stdout.write(self.style.SUCCESS('✓ Тест пройден! Заказ отменён.'))
            else:
                self.stdout.write(self.style.ERROR('✗ Тест не пройден! Заказ не отменился.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Ошибка при создании заказа: {e}'))

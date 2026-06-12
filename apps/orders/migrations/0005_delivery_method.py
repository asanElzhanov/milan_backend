from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


DELIVERY_METHODS = [
    {
        'name': 'Курьерская доставка',
        'code': 'courier',
        'slug': 'courier',
        'delivery_type': 'courier',
        'description': '',
        'is_active': True,
        'base_price': Decimal('0.00'),
        'price_type': 'manager_calculation',
        'free_from_amount': None,
        'sort_order': 10,
    },
    {
        'name': 'Самовывоз',
        'code': 'pickup',
        'slug': 'pickup',
        'delivery_type': 'pickup',
        'description': '',
        'is_active': True,
        'base_price': Decimal('0.00'),
        'price_type': 'free',
        'free_from_amount': None,
        'sort_order': 20,
    },
    {
        'name': 'Доставка по Казахстану',
        'code': 'kazakhstan_delivery',
        'slug': 'kazakhstan-delivery',
        'delivery_type': 'kazakhstan_delivery',
        'description': '',
        'is_active': True,
        'base_price': Decimal('0.00'),
        'price_type': 'manager_calculation',
        'free_from_amount': None,
        'sort_order': 30,
    },
]


def seed_delivery_methods(apps, schema_editor):
    DeliveryMethod = apps.get_model('orders', 'DeliveryMethod')
    Order = apps.get_model('orders', 'Order')

    methods_by_code = {}
    for method_data in DELIVERY_METHODS:
        method, _ = DeliveryMethod.objects.update_or_create(
            code=method_data['code'],
            defaults=method_data,
        )
        methods_by_code[method.code] = method

    legacy_map = {
        'courier': 'courier',
        'pickup': 'pickup',
        'kazakhstan_delivery': 'kazakhstan_delivery',
    }
    for order in Order.objects.all().iterator():
        method = methods_by_code.get(legacy_map.get(order.delivery_method))
        if method is None:
            continue
        order.delivery_method_ref = method
        order.delivery_method_name = method.name
        order.save(update_fields=['delivery_method_ref', 'delivery_method_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_update_order_status_history'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='название')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='код')),
                ('slug', models.SlugField(max_length=80, unique=True, verbose_name='slug')),
                (
                    'delivery_type',
                    models.CharField(
                        choices=[
                            ('courier', 'Курьер'),
                            ('pickup', 'Самовывоз'),
                            ('kazakhstan_delivery', 'Доставка по Казахстану'),
                        ],
                        max_length=32,
                        verbose_name='тип доставки',
                    ),
                ),
                ('description', models.TextField(blank=True, verbose_name='описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='активен')),
                (
                    'base_price',
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal('0.00'),
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                        verbose_name='базовая цена',
                    ),
                ),
                (
                    'price_type',
                    models.CharField(
                        choices=[
                            ('fixed', 'Фиксированная'),
                            ('manager_calculation', 'Уточняется менеджером'),
                            ('free', 'Бесплатная'),
                        ],
                        default='fixed',
                        max_length=32,
                        verbose_name='тип цены',
                    ),
                ),
                (
                    'free_from_amount',
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                        verbose_name='бесплатно от суммы',
                    ),
                ),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='порядок')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='обновлен')),
            ],
            options={
                'verbose_name': 'способ доставки',
                'verbose_name_plural': 'способы доставки',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AlterField(
            model_name='order',
            name='delivery_method',
            field=models.CharField(
                choices=[
                    ('courier', 'Курьер'),
                    ('pickup', 'Самовывоз'),
                    ('kazakhstan_delivery', 'Доставка по Казахстану'),
                    ('post', 'Почта'),
                    ('other', 'Другое'),
                ],
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_method_ref',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='orders',
                to='orders.deliverymethod',
                verbose_name='способ доставки',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_method_name',
            field=models.CharField(blank=True, max_length=120, verbose_name='название способа доставки'),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_price',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='стоимость доставки',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_price_is_final',
            field=models.BooleanField(default=True, verbose_name='стоимость доставки финальная'),
        ),
        migrations.AddIndex(
            model_name='deliverymethod',
            index=models.Index(fields=['code'], name='orders_deli_code_e26177_idx'),
        ),
        migrations.AddIndex(
            model_name='deliverymethod',
            index=models.Index(fields=['slug'], name='orders_deli_slug_73500e_idx'),
        ),
        migrations.AddIndex(
            model_name='deliverymethod',
            index=models.Index(fields=['is_active'], name='orders_deli_is_acti_05610c_idx'),
        ),
        migrations.AddIndex(
            model_name='deliverymethod',
            index=models.Index(fields=['delivery_type'], name='orders_deli_deliver_d26c22_idx'),
        ),
        migrations.AddIndex(
            model_name='deliverymethod',
            index=models.Index(fields=['sort_order'], name='orders_deli_sort_or_0b8728_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['delivery_method_ref'], name='orders_orde_deliver_186dd8_idx'),
        ),
        migrations.AddConstraint(
            model_name='deliverymethod',
            constraint=models.CheckConstraint(check=Q(('base_price__gte', 0)), name='delivery_method_base_price_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='deliverymethod',
            constraint=models.CheckConstraint(
                check=Q(free_from_amount__isnull=True) | Q(free_from_amount__gte=0),
                name='delivery_method_free_from_amount_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=Q(('delivery_price__gte', 0)), name='order_delivery_price_non_negative'),
        ),
        migrations.RunPython(seed_delivery_methods, migrations.RunPython.noop),
    ]

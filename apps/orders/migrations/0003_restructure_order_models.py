from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


def populate_order_snapshots(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    OrderItem = apps.get_model('orders', 'OrderItem')
    OrderStatusHistory = apps.get_model('orders', 'OrderStatusHistory')

    for order in Order.objects.all().iterator():
        customer_name = f'{order.first_name} {order.last_name}'.strip()
        order.customer_name = customer_name or order.email
        order.city = order.delivery_city
        if order.delivery_method == 'kazpost':
            order.delivery_method = 'post'
        elif order.delivery_method == 'dhl':
            order.delivery_method = 'other'
        if order.status == 'pending':
            order.status = 'new'
        elif order.status == 'confirmed':
            order.status = 'processing'
        elif order.status == 'delivered':
            order.status = 'completed'
        elif order.status == 'refunded':
            order.status = 'returned'
        if order.status == 'paid':
            order.payment_status = 'paid'
        order.save(update_fields=['customer_name', 'city', 'delivery_method', 'status', 'payment_status'])

    for item in OrderItem.objects.select_related('product', 'variant', 'variant__product', 'variant__size').iterator():
        product = item.variant.product if item.variant_id else item.product
        item.product_slug = product.slug if product else ''
        if item.variant_id:
            item.sku = item.variant.sku
            item.size_name = item.variant.size.value if item.variant.size_id else item.size_name
        item.save(update_fields=['product_slug', 'sku', 'size_name'])

    status_map = {
        'pending': 'new',
        'confirmed': 'processing',
        'delivered': 'completed',
        'refunded': 'returned',
    }
    for old_status, new_status in status_map.items():
        OrderStatusHistory.objects.filter(status=old_status).update(status=new_status)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_add_catalog_filter_indexes'),
        ('orders', '0002_update_cart_models'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='number',
            new_name='order_number',
        ),
        migrations.RenameField(
            model_name='order',
            old_name='total',
            new_name='total_amount',
        ),
        migrations.RenameField(
            model_name='orderitem',
            old_name='product_sku',
            new_name='sku',
        ),
        migrations.RenameField(
            model_name='orderitem',
            old_name='size_value',
            new_name='size_name',
        ),
        migrations.AddField(
            model_name='order',
            name='customer_name',
            field=models.CharField(default='', max_length=255, verbose_name='имя покупателя'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='city',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='город'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('unpaid', 'Не оплачен'),
                    ('waiting', 'Ожидает оплаты'),
                    ('paid', 'Оплачен'),
                    ('failed', 'Ошибка оплаты'),
                    ('refunded', 'Возвращён'),
                    ('cancelled', 'Отменён'),
                ],
                default='unpaid',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='product_slug',
            field=models.SlugField(default='', max_length=280),
            preserve_default=False,
        ),
        migrations.RunPython(populate_order_snapshots, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name='order',
            name='orders_orde_user_id_0ae59f_idx',
        ),
        migrations.RemoveIndex(
            model_name='order',
            name='orders_orde_status_c6dd84_idx',
        ),
        migrations.RemoveIndex(
            model_name='order',
            name='orders_orde_number_539d36_idx',
        ),
        migrations.RemoveField(
            model_name='order',
            name='delivery_city',
        ),
        migrations.RemoveField(
            model_name='order',
            name='delivery_country',
        ),
        migrations.RemoveField(
            model_name='order',
            name='delivery_postal_code',
        ),
        migrations.RemoveField(
            model_name='order',
            name='delivery_cost',
        ),
        migrations.RemoveField(
            model_name='order',
            name='discount_amount',
        ),
        migrations.RemoveField(
            model_name='order',
            name='first_name',
        ),
        migrations.RemoveField(
            model_name='order',
            name='last_name',
        ),
        migrations.RemoveField(
            model_name='order',
            name='promo_code',
        ),
        migrations.RemoveField(
            model_name='order',
            name='subtotal',
        ),
        migrations.RemoveField(
            model_name='order',
            name='tracking_number',
        ),
        migrations.RemoveField(
            model_name='orderitem',
            name='product',
        ),
        migrations.AlterModelOptions(
            name='orderitem',
            options={'ordering': ['id'], 'verbose_name': 'позиция заказа', 'verbose_name_plural': 'позиции заказа'},
        ),
        migrations.AlterField(
            model_name='order',
            name='delivery_method',
            field=models.CharField(
                choices=[
                    ('courier', 'Курьер'),
                    ('pickup', 'Самовывоз'),
                    ('post', 'Почта'),
                    ('other', 'Другое'),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='email',
            field=models.EmailField(max_length=254, verbose_name='email'),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_number',
            field=models.CharField(editable=False, max_length=20, unique=True, verbose_name='номер заказа'),
        ),
        migrations.AlterField(
            model_name='order',
            name='phone',
            field=models.CharField(max_length=30, verbose_name='телефон'),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'Новый'),
                    ('waiting_payment', 'Ожидает оплаты'),
                    ('paid', 'Оплачен'),
                    ('processing', 'В обработке'),
                    ('shipped', 'Отправлен'),
                    ('completed', 'Завершён'),
                    ('cancelled', 'Отменён'),
                    ('returned', 'Возврат'),
                ],
                default='new',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='total_amount',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
            ),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='quantity',
            field=models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='sku',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='size_name',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='total_price',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
            ),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='unit_price',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
            ),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='variant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='order_items',
                to='catalog.productvariant',
            ),
        ),
        migrations.AlterField(
            model_name='orderstatushistory',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'Новый'),
                    ('waiting_payment', 'Ожидает оплаты'),
                    ('paid', 'Оплачен'),
                    ('processing', 'В обработке'),
                    ('shipped', 'Отправлен'),
                    ('completed', 'Завершён'),
                    ('cancelled', 'Отменён'),
                    ('returned', 'Возврат'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['order_number'], name='orders_orde_order_n_f3ada5_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['user'], name='orders_orde_user_id_a87c6f_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['status'], name='orders_orde_status_c6dd84_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['payment_status'], name='orders_orde_payment_bc131d_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['created_at'], name='orders_orde_created_0e92de_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['phone'], name='orders_orde_phone_7bc88b_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['email'], name='orders_orde_email_88c705_idx'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=Q(('total_amount__gte', 0)), name='order_total_amount_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(check=Q(('quantity__gt', 0)), name='order_item_quantity_positive'),
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(check=Q(('unit_price__gte', 0)), name='order_item_unit_price_non_negative'),
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(check=Q(('total_price__gte', 0)), name='order_item_total_price_non_negative'),
        ),
    ]

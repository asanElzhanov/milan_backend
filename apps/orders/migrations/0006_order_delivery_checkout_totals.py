from decimal import Decimal

import django.core.validators
from django.db import migrations, models
from django.db.models import Q


def populate_order_delivery_snapshots(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    for order in Order.objects.select_related('delivery_method_ref').iterator():
        delivery_price = order.delivery_price or Decimal('0.00')
        order.delivery_method_code = order.delivery_method
        if order.delivery_method_ref_id:
            order.delivery_method_code = order.delivery_method_ref.code
            if not order.delivery_method_name:
                order.delivery_method_name = order.delivery_method_ref.name
        order.delivery_requires_manager_calculation = not order.delivery_price_is_final
        order.items_total = max(order.total_amount - delivery_price, Decimal('0.00'))
        order.save(
            update_fields=[
                'delivery_method_code',
                'delivery_method_name',
                'delivery_requires_manager_calculation',
                'items_total',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_delivery_method'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='delivery_method_code',
            field=models.CharField(blank=True, max_length=50, verbose_name='код способа доставки'),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_requires_manager_calculation',
            field=models.BooleanField(default=False, verbose_name='стоимость доставки требует расчета менеджером'),
        ),
        migrations.AddField(
            model_name='order',
            name='items_total',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='сумма товаров',
            ),
        ),
        migrations.RunPython(populate_order_delivery_snapshots, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(check=Q(items_total__gte=0), name='order_items_total_non_negative'),
        ),
    ]

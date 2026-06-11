from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_status_to_new_status(apps, schema_editor):
    OrderStatusHistory = apps.get_model('orders', 'OrderStatusHistory')
    for history in OrderStatusHistory.objects.all().iterator():
        history.new_status = history.status
        history.save(update_fields=['new_status'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('orders', '0003_restructure_order_models'),
    ]

    operations = [
        migrations.RenameField(
            model_name='orderstatushistory',
            old_name='created_by',
            new_name='changed_by',
        ),
        migrations.AddField(
            model_name='orderstatushistory',
            name='old_status',
            field=models.CharField(
                blank=True,
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
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='orderstatushistory',
            name='new_status',
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
            preserve_default=False,
        ),
        migrations.RunPython(copy_status_to_new_status, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='orderstatushistory',
            name='status',
        ),
        migrations.AlterField(
            model_name='orderstatushistory',
            name='changed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='order_status_changes',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='orderstatushistory',
            index=models.Index(fields=['order'], name='orders_orde_order_i_f43086_idx'),
        ),
        migrations.AddIndex(
            model_name='orderstatushistory',
            index=models.Index(fields=['old_status'], name='orders_orde_old_sta_8fefb4_idx'),
        ),
        migrations.AddIndex(
            model_name='orderstatushistory',
            index=models.Index(fields=['new_status'], name='orders_orde_new_sta_58c5a2_idx'),
        ),
        migrations.AddIndex(
            model_name='orderstatushistory',
            index=models.Index(fields=['changed_by'], name='orders_orde_changed_73ab13_idx'),
        ),
        migrations.AddIndex(
            model_name='orderstatushistory',
            index=models.Index(fields=['created_at'], name='orders_orde_created_5bf538_idx'),
        ),
    ]

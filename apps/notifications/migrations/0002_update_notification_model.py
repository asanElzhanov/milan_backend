import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def migrate_legacy_event_types(apps, schema_editor):
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.filter(event_type='order').update(event_type='order_created')
    Notification.objects.filter(event_type='promo').update(event_type='system')


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='notification',
            old_name='user',
            new_name='recipient',
        ),
        migrations.RenameField(
            model_name='notification',
            old_name='type',
            new_name='event_type',
        ),
        migrations.AlterField(
            model_name='notification',
            name='recipient',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications',
                to=settings.AUTH_USER_MODEL,
                verbose_name='recipient',
            ),
        ),
        migrations.AddField(
            model_name='notification',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('customer', 'Customer'),
                    ('manager', 'Manager'),
                    ('admin', 'Admin'),
                    ('staff', 'Staff'),
                ],
                max_length=20,
                null=True,
                verbose_name='role',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('order_created', 'Order created'),
                    ('order_paid', 'Order paid'),
                    ('order_status_changed', 'Order status changed'),
                    ('order_cancelled', 'Order cancelled'),
                    ('payment_success', 'Payment success'),
                    ('payment_error', 'Payment error'),
                    ('review_created', 'Review created'),
                    ('review_published', 'Review published'),
                    ('review_rejected', 'Review rejected'),
                    ('low_stock', 'Low stock'),
                    ('import_error', 'Import error'),
                    ('system', 'System'),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(migrate_legacy_event_types, migrations.RunPython.noop),
        migrations.AddField(
            model_name='notification',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='notification',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'уведомление',
                'verbose_name_plural': 'уведомления',
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient'], name='notificatio_recipie_be3f1a_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['role'], name='notificatio_role_eeb054_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['event_type'], name='notificatio_event_t_c22bab_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['is_read'], name='notificatio_is_read_9edb86_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['created_at'], name='notificatio_created_46ad24_idx'),
        ),
    ]

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('catalog', '0009_add_product_media'),
    ]

    operations = [
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)], verbose_name='количество')),
                ('operation_type', models.CharField(choices=[('income', 'Приход'), ('sale', 'Продажа'), ('return', 'Возврат'), ('manual_adjustment', 'Ручная корректировка'), ('order_cancel', 'Отмена заказа')], max_length=32, verbose_name='тип операции')),
                ('comment', models.TextField(blank=True, verbose_name='комментарий')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='создано')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to=settings.AUTH_USER_MODEL, verbose_name='пользователь')),
                ('variant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='catalog.productvariant', verbose_name='вариант товара')),
            ],
            options={
                'verbose_name': 'движение остатка',
                'verbose_name_plural': 'движения остатков',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['variant'], name='catalog_sto_variant_c5b1a6_idx'),
                    models.Index(fields=['operation_type'], name='catalog_sto_operati_f0fe92_idx'),
                    models.Index(fields=['created_at'], name='catalog_sto_created_2e9d72_idx'),
                    models.Index(fields=['user'], name='catalog_sto_user_id_798fa2_idx'),
                ],
                'constraints': [
                    models.CheckConstraint(check=models.Q(('quantity__gt', 0)), name='stock_movement_quantity_positive'),
                ],
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0012_multilang_delivery_method'),
    ]

    operations = [
        migrations.AlterField(
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
                    ('expired', 'Время оплаты истекло'),
                ],
                default='unpaid',
                max_length=20,
            ),
        ),
    ]

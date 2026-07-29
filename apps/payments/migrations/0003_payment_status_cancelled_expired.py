from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_provider_freedom_only'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Ожидает'),
                    ('success', 'Успешно'),
                    ('failed', 'Ошибка'),
                    ('refunded', 'Возврат'),
                    ('cancelled', 'Отменён'),
                    ('expired', 'Время оплаты истекло'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]

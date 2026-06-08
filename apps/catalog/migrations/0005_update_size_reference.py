import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_update_color_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='size',
            name='size_type',
            field=models.CharField(
                choices=[
                    ('shoes', 'Обувь'),
                    ('clothes', 'Одежда'),
                    ('accessories', 'Аксессуары'),
                ],
                default='shoes',
                max_length=20,
                verbose_name='тип размера',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='size',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='активен'),
        ),
        migrations.AddField(
            model_name='size',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='создан',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='size',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name='обновлен',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='size',
            name='value',
            field=models.CharField(max_length=20, verbose_name='значение'),
        ),
        migrations.AlterModelOptions(
            name='size',
            options={
                'ordering': ['size_type', 'sort_order', 'value'],
                'verbose_name': 'размер',
                'verbose_name_plural': 'размеры',
            },
        ),
        migrations.AddConstraint(
            model_name='size',
            constraint=models.UniqueConstraint(
                fields=('value', 'size_type'),
                name='unique_size_value_type',
            ),
        ),
    ]

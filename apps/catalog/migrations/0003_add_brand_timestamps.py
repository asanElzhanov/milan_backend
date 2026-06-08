import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_update_category_mptt_seo_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='brand',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='создан',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='brand',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name='обновлен',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='brand',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='активен'),
        ),
    ]

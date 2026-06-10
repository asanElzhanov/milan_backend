import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0008_update_product_image_gallery'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductMedia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('media_type', models.CharField(choices=[('image', 'Изображение'), ('video', 'Видео')], max_length=10, verbose_name='тип медиа')),
                ('file', models.FileField(blank=True, upload_to='products/media/%Y/%m/%d/', verbose_name='файл')),
                ('url', models.URLField(blank=True, verbose_name='ссылка')),
                ('title', models.CharField(blank=True, max_length=200, verbose_name='заголовок')),
                ('alt_text', models.CharField(blank=True, max_length=200, verbose_name='alt text')),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True, verbose_name='активно')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='обновлено')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='media', to='catalog.product')),
            ],
            options={
                'verbose_name': 'медиа товара',
                'verbose_name_plural': 'медиа товаров',
                'ordering': ['sort_order', 'id'],
                'indexes': [
                    models.Index(fields=['product', 'sort_order'], name='product_media_product_sort_idx'),
                    models.Index(fields=['media_type'], name='product_media_type_idx'),
                    models.Index(fields=['is_active'], name='product_media_active_idx'),
                ],
                'constraints': [
                    models.CheckConstraint(
                        check=models.Q(('file', ''), _negated=True) | models.Q(('url', ''), _negated=True),
                        name='product_media_file_or_url_required',
                    ),
                ],
            },
        ),
    ]

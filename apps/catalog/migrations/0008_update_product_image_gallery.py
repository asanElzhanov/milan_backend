import django.utils.timezone
from django.db import migrations, models


def normalize_main_images(apps, schema_editor):
    ProductImage = apps.get_model('catalog', 'ProductImage')
    main_images = (
        ProductImage.objects.filter(is_main=True)
        .order_by('product_id', 'sort_order', 'id')
        .values_list('product_id', 'id')
    )
    seen_products = set()
    duplicate_ids = []

    for product_id, image_id in main_images:
        if product_id in seen_products:
            duplicate_ids.append(image_id)
        else:
            seen_products.add(product_id)

    if duplicate_ids:
        ProductImage.objects.filter(id__in=duplicate_ids).update(is_main=False)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_update_product_variant_reference'),
    ]

    operations = [
        migrations.RenameField(
            model_name='productimage',
            old_name='alt',
            new_name='alt_text',
        ),
        migrations.AddField(
            model_name='productimage',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='создано',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='productimage',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name='обновлено',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='productimage',
            name='alt_text',
            field=models.CharField(blank=True, max_length=200, verbose_name='alt text'),
        ),
        migrations.AlterField(
            model_name='productimage',
            name='image',
            field=models.ImageField(upload_to='products/images/%Y/%m/%d/', verbose_name='изображение'),
        ),
        migrations.AlterModelOptions(
            name='productimage',
            options={
                'ordering': ['sort_order', 'id'],
                'verbose_name': 'изображение товара',
                'verbose_name_plural': 'изображения товаров',
            },
        ),
        migrations.RunPython(normalize_main_images, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='productimage',
            index=models.Index(fields=['product', 'sort_order'], name='catalog_pro_product_4ee3b8_idx'),
        ),
        migrations.AddConstraint(
            model_name='productimage',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_main', True)),
                fields=('product',),
                name='unique_main_image_per_product',
            ),
        ),
    ]

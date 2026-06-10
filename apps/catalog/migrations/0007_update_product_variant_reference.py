from decimal import Decimal

import django.core.validators
import django.utils.timezone
from django.db import migrations, models


def normalize_variant_data(apps, schema_editor):
    ProductVariant = apps.get_model('catalog', 'ProductVariant')
    used_skus = set()

    for variant in ProductVariant.objects.select_related('product').order_by('id'):
        raw_sku = (variant.sku or '').strip()
        base_sku = raw_sku or f'{variant.product.sku}-{variant.id}'
        base_sku = base_sku[:100] or f'variant-{variant.id}'
        sku = base_sku
        counter = 2

        while sku in used_skus or ProductVariant.objects.filter(sku=sku).exclude(pk=variant.pk).exists():
            suffix = f'-{counter}'
            sku = f'{base_sku[:100 - len(suffix)]}{suffix}'
            counter += 1

        used_skus.add(sku)
        variant.sku = sku

        if variant.variant_price == Decimal('0'):
            variant.variant_price = None
        elif variant.variant_price is not None:
            variant.variant_price = variant.product.price + variant.variant_price

        variant.save(update_fields=['sku', 'variant_price'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_product_seo_description_product_seo_title_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='productvariant',
            old_name='stock',
            new_name='stock_quantity',
        ),
        migrations.RenameField(
            model_name='productvariant',
            old_name='sku_variant',
            new_name='sku',
        ),
        migrations.RenameField(
            model_name='productvariant',
            old_name='extra_price',
            new_name='variant_price',
        ),
        migrations.AddField(
            model_name='productvariant',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='активен'),
        ),
        migrations.AddField(
            model_name='productvariant',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='создан',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='productvariant',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name='обновлен',
            ),
            preserve_default=False,
        ),
        migrations.RunPython(normalize_variant_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='productvariant',
            name='sku',
            field=models.CharField(max_length=100, unique=True, verbose_name='артикул варианта'),
        ),
        migrations.AlterField(
            model_name='productvariant',
            name='stock_quantity',
            field=models.PositiveIntegerField(default=0, verbose_name='остаток'),
        ),
        migrations.AlterField(
            model_name='productvariant',
            name='variant_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='цена варианта',
            ),
        ),
        migrations.AlterModelOptions(
            name='productvariant',
            options={
                'verbose_name': 'вариант товара',
                'verbose_name_plural': 'варианты товаров',
            },
        ),
        migrations.RemoveIndex(
            model_name='productvariant',
            name='catalog_pro_product_ee4f5c_idx',
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['sku'], name='catalog_pro_sku_187601_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['product'], name='catalog_pro_product_460665_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['is_active'], name='catalog_pro_is_acti_ce92a3_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['stock_quantity'], name='catalog_pro_stock_q_6ded5d_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['product', 'stock_quantity'], name='catalog_pro_product_ee4f5c_idx'),
        ),
        migrations.AddConstraint(
            model_name='productvariant',
            constraint=models.CheckConstraint(
                check=models.Q(('stock_quantity__gte', 0)),
                name='product_variant_stock_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='productvariant',
            constraint=models.CheckConstraint(
                check=models.Q(('variant_price__isnull', True), ('variant_price__gte', 0), _connector='OR'),
                name='product_variant_price_non_negative',
            ),
        ),
    ]

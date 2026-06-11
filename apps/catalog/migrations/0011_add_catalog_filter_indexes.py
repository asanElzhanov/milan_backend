from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0010_add_stock_movement'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['is_active', 'price'],
                name='cat_product_active_price_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_new'], name='catalog_product_is_new_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(
                fields=['product', 'is_active', 'stock_quantity'],
                name='cat_var_stock_lookup_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(
                fields=['size', 'is_active', 'product'],
                name='cat_var_size_lookup_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(
                fields=['color', 'is_active', 'product'],
                name='cat_var_color_lookup_idx',
            ),
        ),
    ]

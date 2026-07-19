from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0016_delete_legacy_promo'),
    ]

    operations = [
        # --- Category ---
        migrations.RenameField('category', old_name='name', new_name='name_ru'),
        migrations.RenameField('category', old_name='description', new_name='description_ru'),
        migrations.AddField(
            model_name='category',
            name='name_kz',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='название (каз.)'),
        ),
        migrations.AddField(
            model_name='category',
            name='name_en',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='название (англ.)'),
        ),
        migrations.AddField(
            model_name='category',
            name='description_kz',
            field=models.TextField(blank=True, default='', verbose_name='описание (каз.)'),
        ),
        migrations.AddField(
            model_name='category',
            name='description_en',
            field=models.TextField(blank=True, default='', verbose_name='описание (англ.)'),
        ),
        # --- Brand ---
        migrations.RenameField('brand', old_name='name', new_name='name_ru'),
        migrations.AddField(
            model_name='brand',
            name='name_kz',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='название (каз.)'),
        ),
        migrations.AddField(
            model_name='brand',
            name='name_en',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='название (англ.)'),
        ),
        # --- Color ---
        migrations.RenameField('color', old_name='name', new_name='name_ru'),
        migrations.AddField(
            model_name='color',
            name='name_kz',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='название (каз.)'),
        ),
        migrations.AddField(
            model_name='color',
            name='name_en',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='название (англ.)'),
        ),
        # --- Product ---
        migrations.RenameField('product', old_name='name', new_name='name_ru'),
        migrations.RenameField('product', old_name='description', new_name='description_ru'),
        migrations.RenameField('product', old_name='composition', new_name='composition_ru'),
        migrations.RenameField('product', old_name='material', new_name='material_ru'),
        migrations.AddField(
            model_name='product',
            name='name_kz',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='название (каз.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='name_en',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='название (англ.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='description_kz',
            field=models.TextField(blank=True, default='', verbose_name='описание (каз.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='description_en',
            field=models.TextField(blank=True, default='', verbose_name='описание (англ.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='composition_kz',
            field=models.TextField(blank=True, default='', verbose_name='состав (каз.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='composition_en',
            field=models.TextField(blank=True, default='', verbose_name='состав (англ.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='material_kz',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='материал (каз.)'),
        ),
        migrations.AddField(
            model_name='product',
            name='material_en',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='материал (англ.)'),
        ),
        # --- ProductMedia ---
        migrations.RenameField('productmedia', old_name='title', new_name='title_ru'),
        migrations.AddField(
            model_name='productmedia',
            name='title_kz',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='заголовок (каз.)'),
        ),
        migrations.AddField(
            model_name='productmedia',
            name='title_en',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='заголовок (англ.)'),
        ),
        # --- Banner ---
        migrations.RenameField('banner', old_name='title', new_name='title_ru'),
        migrations.RenameField('banner', old_name='subtitle', new_name='subtitle_ru'),
        migrations.RenameField('banner', old_name='button_text', new_name='button_text_ru'),
        migrations.AddField(
            model_name='banner',
            name='title_kz',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='заголовок (каз.)'),
        ),
        migrations.AddField(
            model_name='banner',
            name='title_en',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='заголовок (англ.)'),
        ),
        migrations.AddField(
            model_name='banner',
            name='subtitle_kz',
            field=models.CharField(blank=True, default='', max_length=300, verbose_name='подзаголовок (каз.)'),
        ),
        migrations.AddField(
            model_name='banner',
            name='subtitle_en',
            field=models.CharField(blank=True, default='', max_length=300, verbose_name='подзаголовок (англ.)'),
        ),
        migrations.AddField(
            model_name='banner',
            name='button_text_kz',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='текст кнопки (каз.)'),
        ),
        migrations.AddField(
            model_name='banner',
            name='button_text_en',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='текст кнопки (англ.)'),
        ),
        # --- Meta.ordering updates for renamed fields ---
        migrations.AlterModelOptions(
            name='category',
            options={'ordering': ['sort_order', 'name_ru'], 'verbose_name': 'категория', 'verbose_name_plural': 'категории'},
        ),
        migrations.AlterModelOptions(
            name='brand',
            options={'ordering': ['name_ru'], 'verbose_name': 'бренд', 'verbose_name_plural': 'бренды'},
        ),
        migrations.AlterModelOptions(
            name='color',
            options={'ordering': ['name_ru'], 'verbose_name': 'цвет', 'verbose_name_plural': 'цвета'},
        ),
    ]

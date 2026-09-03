from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0011_order_order_pay_status_created_idx_and_more'),
    ]

    operations = [
        migrations.RenameField('deliverymethod', old_name='name', new_name='name_ru'),
        migrations.RenameField('deliverymethod', old_name='description', new_name='description_ru'),
        migrations.AddField(
            model_name='deliverymethod',
            name='name_kz',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='название (каз.)'),
        ),
        migrations.AddField(
            model_name='deliverymethod',
            name='name_en',
            field=models.CharField(blank=True, default='', max_length=120, verbose_name='название (англ.)'),
        ),
        migrations.AddField(
            model_name='deliverymethod',
            name='description_kz',
            field=models.TextField(blank=True, default='', verbose_name='описание (каз.)'),
        ),
        migrations.AddField(
            model_name='deliverymethod',
            name='description_en',
            field=models.TextField(blank=True, default='', verbose_name='описание (англ.)'),
        ),
        migrations.AlterModelOptions(
            name='deliverymethod',
            options={'ordering': ['sort_order', 'name_ru'], 'verbose_name': 'способ доставки', 'verbose_name_plural': 'способы доставки'},
        ),
    ]

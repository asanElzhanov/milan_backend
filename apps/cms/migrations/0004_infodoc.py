from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0003_static_page_blocks'),
    ]

    operations = [
        migrations.CreateModel(
            name='InfoDoc',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title_ru', models.CharField(max_length=255, verbose_name='название')),
                ('title_kz', models.CharField(blank=True, default='', max_length=255, verbose_name='название (каз.)')),
                ('title_en', models.CharField(blank=True, default='', max_length=255, verbose_name='название (англ.)')),
                ('file', models.FileField(upload_to='info_docs/%Y/%m/%d/', verbose_name='файл')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='порядок')),
                ('is_active', models.BooleanField(default=True, verbose_name='активен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='обновлён')),
            ],
            options={
                'verbose_name': 'информационный документ',
                'verbose_name_plural': 'информационные документы',
                'ordering': ['sort_order', 'id'],
                'indexes': [models.Index(fields=['is_active', 'sort_order'], name='cms_infodoc_active_order_idx')],
            },
        ),
    ]

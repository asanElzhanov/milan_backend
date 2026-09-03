import django.db.models.deletion
from django.db import migrations, models


DEFAULT_PAGES = (
    {
        'slug': 'about',
        'title_ru': 'О компании',
        'title_kz': 'Компания туралы',
        'title_en': 'About company',
    },
    {
        'slug': 'delivery',
        'title_ru': 'Доставка',
        'title_kz': 'Жеткізу',
        'title_en': 'Delivery',
    },
    {
        'slug': 'payment',
        'title_ru': 'Оплата',
        'title_kz': 'Төлем',
        'title_en': 'Payment',
    },
    {
        'slug': 'faq',
        'title_ru': 'Частые вопросы',
        'title_kz': 'Жиі қойылатын сұрақтар',
        'title_en': 'FAQ',
    },
    {
        'slug': 'contacts',
        'title_ru': 'Контакты',
        'title_kz': 'Байланыстар',
        'title_en': 'Contacts',
    },
)


def create_default_pages(apps, schema_editor):
    StaticPage = apps.get_model('cms', 'StaticPage')
    for page in DEFAULT_PAGES:
        StaticPage.objects.get_or_create(
            slug=page['slug'],
            defaults={
                **page,
                'content_ru': '',
                'content_kz': '',
                'content_en': '',
                'is_active': True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0002_multilang_static_page'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staticpage',
            name='content_ru',
            field=models.TextField(blank=True, default='', verbose_name='вводный текст'),
        ),
        migrations.CreateModel(
            name='StaticPageBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title_ru', models.CharField(max_length=255, verbose_name='заголовок')),
                ('title_kz', models.CharField(blank=True, default='', max_length=255, verbose_name='заголовок (каз.)')),
                ('title_en', models.CharField(blank=True, default='', max_length=255, verbose_name='заголовок (англ.)')),
                ('content_ru', models.TextField(verbose_name='основной текст')),
                ('content_kz', models.TextField(blank=True, default='', verbose_name='основной текст (каз.)')),
                ('content_en', models.TextField(blank=True, default='', verbose_name='основной текст (англ.)')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='порядок')),
                ('is_active', models.BooleanField(default=True, verbose_name='активен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='обновлён')),
                ('page', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks', to='cms.staticpage', verbose_name='страница')),
            ],
            options={
                'verbose_name': 'блок статической страницы',
                'verbose_name_plural': 'блоки статической страницы',
                'ordering': ['sort_order', 'id'],
                'indexes': [models.Index(fields=['page', 'is_active', 'sort_order'], name='cms_block_active_order_idx')],
            },
        ),
        migrations.RunPython(create_default_pages, migrations.RunPython.noop),
    ]

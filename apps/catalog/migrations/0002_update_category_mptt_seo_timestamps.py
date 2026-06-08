import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='category',
            old_name='meta_title',
            new_name='seo_title',
        ),
        migrations.RenameField(
            model_name='category',
            old_name='meta_description',
            new_name='seo_description',
        ),
        migrations.AddField(
            model_name='category',
            name='seo_keywords',
            field=models.CharField(blank=True, max_length=255, verbose_name='SEO keywords'),
        ),
        migrations.AddField(
            model_name='category',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='создана',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='category',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name='обновлена',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='category',
            name='seo_description',
            field=models.TextField(blank=True, verbose_name='SEO description'),
        ),
        migrations.AlterField(
            model_name='category',
            name='seo_title',
            field=models.CharField(blank=True, max_length=200, verbose_name='SEO title'),
        ),
        migrations.AlterModelOptions(
            name='category',
            options={
                'ordering': ['sort_order', 'name'],
                'verbose_name': 'категория',
                'verbose_name_plural': 'категории',
            },
        ),
    ]

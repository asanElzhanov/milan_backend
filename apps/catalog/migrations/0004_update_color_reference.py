import django.core.validators
import django.utils.text
import django.utils.timezone
from django.db import migrations, models


def fill_color_slugs(apps, schema_editor):
    Color = apps.get_model('catalog', 'Color')
    used_slugs = set()

    for color in Color.objects.order_by('id'):
        base_slug = django.utils.text.slugify(color.name, allow_unicode=True) or f'color-{color.id}'
        slug = base_slug
        counter = 2
        while slug in used_slugs or Color.objects.filter(slug=slug).exclude(pk=color.pk).exists():
            slug = f'{base_slug}-{counter}'
            counter += 1

        color.slug = slug
        color.save(update_fields=['slug'])
        used_slugs.add(slug)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_add_brand_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='color',
            name='slug',
            field=models.SlugField(blank=True, max_length=80, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='color',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='активен'),
        ),
        migrations.AddField(
            model_name='color',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                verbose_name='создан',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='color',
            name='updated_at',
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
                verbose_name='обновлен',
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_color_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='color',
            name='hex_code',
            field=models.CharField(
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message='Введите HEX-цвет в формате #FFFFFF.',
                        regex='^#[0-9A-Fa-f]{6}$',
                    ),
                ],
                verbose_name='hex',
            ),
        ),
        migrations.AlterField(
            model_name='color',
            name='slug',
            field=models.SlugField(max_length=80, unique=True),
        ),
        migrations.AlterModelOptions(
            name='color',
            options={
                'ordering': ['name'],
                'verbose_name': 'цвет',
                'verbose_name_plural': 'цвета',
            },
        ),
    ]

from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0017_multilang_name_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productimage',
            name='image',
            field=models.FileField(
                upload_to='products/images/%Y/%m/%d/',
                validators=[FileExtensionValidator(
                    allowed_extensions=('jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'mp4', 'webm', 'mov', 'm4v', 'ogv'),
                )],
                verbose_name='медиафайл',
            ),
        ),
        migrations.AlterField(
            model_name='banner',
            name='image',
            field=models.FileField(
                upload_to='banners/%Y/%m/%d/',
                validators=[FileExtensionValidator(
                    allowed_extensions=('jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'mp4', 'webm', 'mov', 'm4v', 'ogv'),
                )],
                verbose_name='медиафайл',
            ),
        ),
        migrations.AlterField(
            model_name='banner',
            name='image_mobile',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='banners/%Y/%m/%d/',
                validators=[FileExtensionValidator(
                    allowed_extensions=('jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'mp4', 'webm', 'mov', 'm4v', 'ogv'),
                )],
                verbose_name='мобильный медиафайл',
            ),
        ),
    ]

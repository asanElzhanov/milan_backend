from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0018_product_and_banner_media_files'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reviewimage',
            name='image',
            field=models.FileField(
                upload_to='reviews/%Y/%m/%d/',
                validators=[FileExtensionValidator(
                    allowed_extensions=(
                        'jpg', 'jpeg', 'png', 'webp', 'gif', 'avif',
                        'mp4', 'webm', 'mov', 'm4v', 'ogv',
                    ),
                )],
            ),
        ),
    ]

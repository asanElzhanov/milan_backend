from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0019_review_media_files'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='season',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ss', 'Весна/Лето'),
                    ('aw', 'Осень/Зима'),
                    ('as', 'Осень/Весна'),
                    ('all', 'Всесезонный'),
                ],
                max_length=10,
                verbose_name='сезон',
            ),
        ),
    ]

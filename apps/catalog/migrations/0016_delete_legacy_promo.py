from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0015_alter_importjob_error_report'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Promo',
        ),
    ]

# Generated manually for accounts user role display labels.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('customer', 'Customer'),
                    ('manager', 'Manager'),
                    ('admin', 'Admin'),
                ],
                default='customer',
                max_length=20,
                verbose_name='role',
            ),
        ),
    ]

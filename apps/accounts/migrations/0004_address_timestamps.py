# Generated manually for Address timestamps.

from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='address',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='address',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]

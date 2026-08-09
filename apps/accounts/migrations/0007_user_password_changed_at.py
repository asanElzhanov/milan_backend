# Generated manually for User.password_changed_at.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_wishlist_acct_wish_user_added_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='password_changed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='пароль изменён'),
        ),
    ]

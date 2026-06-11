import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def populate_cart_tokens(apps, schema_editor):
    Cart = apps.get_model('orders', 'Cart')
    for cart in Cart.objects.filter(token__isnull=True):
        cart.token = uuid.uuid4()
        cart.save(update_fields=['token'])


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cart',
            name='session_key',
        ),
        migrations.AddField(
            model_name='cart',
            name='token',
            field=models.UUIDField(blank=True, db_index=True, null=True, verbose_name='guest cart token'),
        ),
        migrations.AddField(
            model_name='cart',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='активна'),
        ),
        migrations.RunPython(populate_cart_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cart',
            name='token',
            field=models.UUIDField(blank=True, db_index=True, default=uuid.uuid4, null=True, unique=True, verbose_name='guest cart token'),
        ),
        migrations.AlterField(
            model_name='cart',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='carts', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='cartitem',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='cartitem',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='cartitem',
            name='cart',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.cart'),
        ),
        migrations.AlterField(
            model_name='cartitem',
            name='variant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cart_items', to='catalog.productvariant'),
        ),
        migrations.AlterModelOptions(
            name='cart',
            options={'verbose_name': 'корзина', 'verbose_name_plural': 'корзины'},
        ),
        migrations.AlterModelOptions(
            name='cartitem',
            options={'verbose_name': 'позиция корзины', 'verbose_name_plural': 'позиции корзины'},
        ),
        migrations.AlterUniqueTogether(
            name='cartitem',
            unique_together=set(),
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['user'], name='orders_cart_user_id_7d3dad_idx'),
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['token'], name='orders_cart_token_5c1a1c_idx'),
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['is_active'], name='orders_cart_is_acti_15a091_idx'),
        ),
        migrations.AddIndex(
            model_name='cartitem',
            index=models.Index(fields=['cart'], name='orders_cart_cart_id_dc9f49_idx'),
        ),
        migrations.AddIndex(
            model_name='cartitem',
            index=models.Index(fields=['variant'], name='orders_cart_variant_339bb5_idx'),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(condition=Q(('is_active', True), ('user__isnull', False)), fields=('user',), name='unique_active_cart_per_user'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.UniqueConstraint(fields=('cart', 'variant'), name='unique_cart_variant'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.CheckConstraint(check=Q(('quantity__gt', 0)), name='cart_item_quantity_positive'),
        ),
    ]

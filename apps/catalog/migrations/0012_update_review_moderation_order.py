from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('orders', '0006_order_delivery_checkout_totals'),
        ('catalog', '0011_add_catalog_filter_indexes'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='review',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'отзыв',
                'verbose_name_plural': 'отзывы',
            },
        ),
        migrations.AlterUniqueTogether(
            name='review',
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name='review',
            name='is_approved',
        ),
        migrations.AddField(
            model_name='review',
            name='moderated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='review',
            name='moderation_comment',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='review',
            name='order',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reviews',
                to='orders.order',
            ),
        ),
        migrations.AddField(
            model_name='review',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'На модерации'),
                    ('published', 'Опубликован'),
                    ('rejected', 'Отклонён'),
                    ('hidden', 'Скрыт'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='review',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name='review',
            name='moderated_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='moderated_reviews',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='review',
            name='rating',
            field=models.PositiveSmallIntegerField(
                validators=[MinValueValidator(1), MaxValueValidator(5)],
            ),
        ),
        migrations.AlterField(
            model_name='review',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='reviews',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['product'], name='catalog_rev_product_14bf05_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['user'], name='catalog_rev_user_id_82176f_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['order'], name='catalog_rev_order_i_151b4b_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['status'], name='catalog_rev_status_99f17b_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['created_at'], name='catalog_rev_created_05b149_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['rating'], name='catalog_rev_rating_ada80b_idx'),
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.UniqueConstraint(
                fields=('product', 'user', 'order'),
                name='unique_review_per_product_user_order',
            ),
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.CheckConstraint(
                check=models.Q(('rating__gte', 1), ('rating__lte', 5)),
                name='review_rating_between_1_and_5',
            ),
        ),
    ]

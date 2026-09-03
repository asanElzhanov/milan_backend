import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import OrderItem

from .constants import (
    EventSource,
    EventType,
    PopularityScope,
    PopularityWindow,
    RecommendationContext,
    RelationType,
)


class UserRecommendation(models.Model):
    tracking_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    generation_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_recommendations',
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='user_recommendations')
    context = models.CharField(max_length=32, choices=RecommendationContext.choices)
    rank = models.PositiveSmallIntegerField()
    score = models.DecimalField(max_digits=18, decimal_places=8)
    reason_code = models.CharField(max_length=32)
    reason_payload = models.JSONField(default=dict, blank=True)
    algorithm_version = models.CharField(max_length=32)
    is_fallback = models.BooleanField(default=False)
    generated_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['rank']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'context', 'generation_id', 'product'],
                name='reco_user_gen_product_uniq',
            ),
            models.UniqueConstraint(
                fields=['user', 'context', 'generation_id', 'rank'],
                name='reco_user_gen_rank_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'context', '-generated_at'], name='reco_user_ctx_gen_idx'),
            models.Index(fields=['user', 'context', 'generation_id', 'rank'], name='reco_user_gen_rank_idx'),
            models.Index(fields=['expires_at'], name='reco_user_expires_idx'),
            models.Index(fields=['generation_id'], name='reco_generation_idx'),
        ]

    def __str__(self):
        return f'{self.user_id}:{self.context}:{self.rank}:{self.product_id}'


class UserProductEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='recommendation_events',
    )
    anonymous_id_hash = models.CharField(max_length=64, blank=True, db_index=True)
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='recommendation_events',
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recommendation_events',
    )
    order_item = models.ForeignKey(
        OrderItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recommendation_events',
    )
    recommendation = models.ForeignKey(
        UserRecommendation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='events',
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    source = models.CharField(max_length=32, choices=EventSource.choices)
    context = models.CharField(max_length=32, choices=RecommendationContext.choices, blank=True)
    value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    client_event_id = models.UUIDField(null=True, blank=True, unique=True)
    deduplication_key = models.CharField(max_length=160, null=True, blank=True, unique=True)
    search_query = models.CharField(max_length=255, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at', '-id']
        constraints = [
            models.CheckConstraint(
                check=Q(user__isnull=False) | ~Q(anonymous_id_hash=''),
                name='reco_event_actor_required',
            ),
            models.CheckConstraint(
                check=Q(event_type=EventType.SEARCH) | Q(product__isnull=False),
                name='reco_event_product_required',
            ),
        ]
        indexes = [
            models.Index(fields=['user', '-occurred_at'], name='reco_event_user_time_idx'),
            models.Index(fields=['product', 'event_type', '-occurred_at'], name='reco_event_product_type_idx'),
            models.Index(fields=['event_type', '-occurred_at'], name='reco_event_type_time_idx'),
            models.Index(fields=['anonymous_id_hash', '-occurred_at'], name='reco_event_anon_time_idx'),
            models.Index(fields=['source', 'context', '-occurred_at'], name='reco_event_source_ctx_idx'),
        ]

    def clean(self):
        super().clean()
        if not self.user_id and not self.anonymous_id_hash:
            raise ValidationError('Событие должно иметь пользователя или анонимного actor.')
        if self.event_type != EventType.SEARCH and not self.product_id:
            raise ValidationError({'product': 'Для этого события товар обязателен.'})

    def __str__(self):
        actor = self.user_id or self.anonymous_id_hash[:8]
        return f'{actor}:{self.event_type}:{self.product_id or "search"}'


class ProductPopularity(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='popularity_rows')
    scope = models.CharField(max_length=16, choices=PopularityScope.choices)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='product_popularity_rows',
    )
    window = models.CharField(max_length=8, choices=PopularityWindow.choices)
    views_count = models.BigIntegerField(default=0)
    search_clicks_count = models.BigIntegerField(default=0)
    favorite_adds_count = models.BigIntegerField(default=0)
    cart_adds_count = models.BigIntegerField(default=0)
    purchases_count = models.BigIntegerField(default=0)
    cancellations_count = models.BigIntegerField(default=0)
    returns_count = models.BigIntegerField(default=0)
    rating_score = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    score = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    window_started_at = models.DateTimeField(null=True, blank=True)
    window_ended_at = models.DateTimeField(null=True, blank=True)
    calculated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'scope', 'window'],
                condition=Q(category__isnull=True),
                name='reco_pop_global_uniq',
            ),
            models.UniqueConstraint(
                fields=['product', 'category', 'scope', 'window'],
                condition=Q(category__isnull=False),
                name='reco_pop_category_uniq',
            ),
            models.CheckConstraint(
                check=(
                    Q(scope=PopularityScope.GLOBAL, category__isnull=True)
                    | Q(scope=PopularityScope.CATEGORY, category__isnull=False)
                ),
                name='reco_pop_scope_category_ck',
            ),
        ]
        indexes = [
            models.Index(fields=['scope', 'category', 'window', '-score'], name='reco_pop_scope_score_idx'),
            models.Index(fields=['product', 'window'], name='reco_pop_product_win_idx'),
            models.Index(fields=['calculated_at'], name='reco_pop_calculated_idx'),
        ]

    def __str__(self):
        return f'{self.product_id}:{self.scope}:{self.window}:{self.score}'


class ProductRelation(models.Model):
    source_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='outgoing_relations')
    target_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='incoming_relations')
    relation_type = models.CharField(max_length=20, choices=RelationType.choices)
    score = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    support_count = models.PositiveIntegerField(default=0)
    confidence = models.DecimalField(max_digits=12, decimal_places=8, default=0)
    components = models.JSONField(default=dict, blank=True)
    window_started_at = models.DateTimeField(null=True, blank=True)
    window_ended_at = models.DateTimeField(null=True, blank=True)
    calculated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['source_product', 'target_product', 'relation_type'],
                name='reco_relation_pair_uniq',
            ),
            models.CheckConstraint(
                check=~Q(source_product=models.F('target_product')),
                name='reco_relation_not_self_ck',
            ),
        ]
        indexes = [
            models.Index(fields=['source_product', 'relation_type', '-score'], name='reco_relation_source_idx'),
            models.Index(fields=['target_product', 'relation_type'], name='reco_relation_target_idx'),
        ]

    def __str__(self):
        return f'{self.source_product_id}->{self.target_product_id}:{self.relation_type}'


class UserCategoryPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='category_preferences',
    )
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='user_preferences')
    score = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    positive_score = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    negative_score = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    events_count = models.PositiveIntegerField(default=0)
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'category'], name='reco_user_category_uniq'),
        ]
        indexes = [
            models.Index(fields=['user', '-score'], name='reco_pref_user_score_idx'),
            models.Index(fields=['category', '-score'], name='reco_pref_category_idx'),
            models.Index(fields=['last_event_at'], name='reco_pref_last_event_idx'),
        ]

    def __str__(self):
        return f'{self.user_id}:{self.category_id}:{self.score}'


class HiddenRecommendation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hidden_recommendations',
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='hidden_by_users')
    context = models.CharField(max_length=32, default='all')
    reason = models.CharField(max_length=64, blank=True)
    source_recommendation = models.ForeignKey(
        UserRecommendation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='hide_records',
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'product', 'context'], name='reco_hidden_user_product_uniq'),
        ]
        indexes = [
            models.Index(fields=['user', 'context', 'expires_at'], name='reco_hidden_user_ctx_idx'),
            models.Index(fields=['product'], name='reco_hidden_product_idx'),
        ]

    def __str__(self):
        return f'{self.user_id}:{self.product_id}:{self.context}'

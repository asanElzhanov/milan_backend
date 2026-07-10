from django.contrib import admin

from .models import (
    HiddenRecommendation,
    ProductPopularity,
    ProductRelation,
    UserCategoryPreference,
    UserProductEvent,
    UserRecommendation,
)


@admin.register(UserProductEvent)
class UserProductEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'user', 'product', 'source', 'context', 'occurred_at')
    list_filter = ('event_type', 'source', 'context', 'occurred_at')
    search_fields = ('user__email', 'product__name', 'deduplication_key')
    readonly_fields = tuple(field.name for field in UserProductEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProductPopularity)
class ProductPopularityAdmin(admin.ModelAdmin):
    list_display = ('product', 'scope', 'category', 'window', 'score', 'calculated_at')
    list_filter = ('scope', 'window', 'calculated_at')
    search_fields = ('product__name',)


@admin.register(ProductRelation)
class ProductRelationAdmin(admin.ModelAdmin):
    list_display = ('source_product', 'target_product', 'relation_type', 'score', 'support_count')
    list_filter = ('relation_type', 'calculated_at')
    search_fields = ('source_product__name', 'target_product__name')


@admin.register(UserCategoryPreference)
class UserCategoryPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'score', 'events_count', 'last_event_at')
    search_fields = ('user__email', 'category__name')


@admin.register(UserRecommendation)
class UserRecommendationAdmin(admin.ModelAdmin):
    list_display = ('user', 'context', 'rank', 'product', 'reason_code', 'generated_at', 'expires_at')
    list_filter = ('context', 'algorithm_version', 'is_fallback')
    search_fields = ('user__email', 'product__name', 'tracking_id', 'generation_id')
    readonly_fields = tuple(field.name for field in UserRecommendation._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(HiddenRecommendation)
class HiddenRecommendationAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'context', 'reason', 'expires_at', 'created_at')
    list_filter = ('context', 'created_at')
    search_fields = ('user__email', 'product__name')

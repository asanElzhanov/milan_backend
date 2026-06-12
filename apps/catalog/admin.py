from django.contrib import admin
from django.db import models
from django.db.models import Exists, OuterRef
from mptt.admin import MPTTModelAdmin
from .models import (
    Banner, Brand, Category, Color, Product, ProductImage,
    ProductMedia, ProductVariant, Promo, Review, Size, StockMovement,
)
from .services import ReviewModerationService


class ProductSaleFilter(admin.SimpleListFilter):
    title = 'распродажа'
    parameter_name = 'is_sale'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Со скидкой'),
            ('no', 'Без скидки'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(old_price__isnull=False, old_price__gt=models.F('price'))
        if self.value() == 'no':
            return queryset.filter(models.Q(old_price__isnull=True) | models.Q(old_price__lte=models.F('price')))
        return queryset


class ProductStockFilter(admin.SimpleListFilter):
    title = 'наличие'
    parameter_name = 'in_stock'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'В наличии'),
            ('no', 'Нет в наличии'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(_admin_in_stock=True)
        if self.value() == 'no':
            return queryset.filter(_admin_in_stock=False)
        return queryset


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    fields = ('size', 'color', 'sku', 'stock_quantity', 'variant_price', 'is_active')
    readonly_fields = ('stock_quantity',)
    autocomplete_fields = ('size', 'color')
    extra = 1


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    fields = ('image', 'is_main', 'sort_order', 'alt_text', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    extra = 1


class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    fields = ('media_type', 'file', 'url', 'title', 'alt_text', 'sort_order', 'is_active', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'slug', 'category', 'brand',
        'price', 'old_price', 'discount_display',
        'is_new', 'is_sale_display', 'is_active', 'in_stock_display',
        'created_at', 'updated_at',
    )
    list_filter = ('category', 'brand', 'is_active', 'is_new', ProductSaleFilter, ProductStockFilter)
    search_fields = ('name', 'slug', 'sku', 'variants__sku')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'is_active', 'is_new')
    readonly_fields = (
        'created_at', 'updated_at',
        'views_count', 'orders_count', 'rating', 'reviews_count',
        'discount_display', 'is_sale_display', 'in_stock_display',
    )
    ordering = ('name',)
    inlines = (ProductVariantInline, ProductImageInline, ProductMediaInline)
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'sku', 'name', 'slug', 'category', 'brand',
                'description', 'composition', 'material', 'season',
            ),
        }),
        ('Цены и скидки', {
            'fields': ('price', 'old_price', 'discount_display'),
        }),
        ('SEO', {
            'fields': ('seo_title', 'seo_description', 'meta_title', 'meta_description'),
        }),
        ('Статусы', {
            'fields': ('is_active', 'is_new', 'is_featured', 'is_sale_display', 'in_stock_display'),
        }),
        ('Системные поля', {
            'fields': ('views_count', 'orders_count', 'rating', 'reviews_count', 'created_at', 'updated_at'),
        }),
    )

    def get_queryset(self, request):
        stock_variants = ProductVariant.objects.filter(
            product=OuterRef('pk'),
            is_active=True,
            stock_quantity__gt=0,
        )
        return super().get_queryset(request).select_related('category', 'brand').annotate(
            _admin_in_stock=Exists(stock_variants),
        )

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), may_have_duplicates

    @admin.display(description='скидка')
    def discount_display(self, obj):
        return f'{obj.discount}%' if obj.discount else '—'

    @admin.display(boolean=True, description='распродажа')
    def is_sale_display(self, obj):
        return obj.is_sale

    @admin.display(boolean=True, description='в наличии')
    def in_stock_display(self, obj):
        return getattr(obj, '_admin_in_stock', False)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'sku', 'size', 'color', 'stock_quantity', 'variant_price', 'is_active', 'in_stock')
    list_filter = ('product__category', 'product__brand', 'size', 'color', 'is_active', ProductStockFilter)
    search_fields = ('sku', 'product__name', 'product__slug')
    autocomplete_fields = ('product', 'size', 'color')
    ordering = ('product__name', 'sku')
    readonly_fields = ('stock_quantity', 'in_stock', 'created_at', 'updated_at')
    fieldsets = (
        ('Вариант', {
            'fields': ('product', 'sku', 'size', 'color', 'variant_price', 'is_active'),
        }),
        ('Остаток', {
            'fields': ('stock_quantity', 'in_stock'),
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product__category', 'product__brand', 'size', 'color',
        ).annotate(
            _admin_in_stock=models.Case(
                models.When(is_active=True, stock_quantity__gt=0, then=models.Value(True)),
                default=models.Value(False),
                output_field=models.BooleanField(),
            ),
        )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'image', 'is_main', 'sort_order', 'alt_text', 'created_at')
    list_filter = ('is_main',)
    search_fields = ('product__name', 'product__slug', 'alt_text')
    autocomplete_fields = ('product',)
    ordering = ('product__name', 'sort_order', 'id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('variant', 'sku', 'product', 'quantity', 'operation_type', 'user', 'comment', 'created_at')
    list_filter = ('operation_type', 'created_at', 'user')
    search_fields = ('variant__sku', 'variant__product__name', 'comment')
    readonly_fields = ('variant', 'quantity', 'operation_type', 'user', 'comment', 'created_at')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('variant__product', 'user')

    @admin.display(description='SKU')
    def sku(self, obj):
        return obj.variant.sku

    @admin.display(description='товар')
    def product(self, obj):
        return obj.variant.product

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductMedia)
class ProductMediaAdmin(admin.ModelAdmin):
    list_display = ('product', 'media_type', 'title', 'is_active', 'sort_order')
    list_filter = ('media_type', 'is_active')
    search_fields = ('product__name', 'title', 'url', 'alt_text')
    autocomplete_fields = ('product',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'user', 'order', 'rating', 'status',
        'created_at', 'moderated_by', 'moderated_at',
    )
    list_filter = (
        'status', 'rating', 'created_at',
    )
    search_fields = (
        'product__name', 'product__slug',
        'user__email', 'user__first_name', 'user__last_name',
        'order__order_number', 'text',
    )
    readonly_fields = (
        'product', 'user', 'order', 'rating', 'text',
        'created_at', 'updated_at', 'moderated_by', 'moderated_at',
    )
    ordering = ('-created_at',)
    actions = ('publish_reviews', 'reject_reviews', 'hide_reviews')
    fieldsets = (
        ('Отзыв', {
            'fields': ('product', 'user', 'order', 'rating', 'text', 'is_verified_purchase'),
        }),
        ('Модерация', {
            'fields': ('status', 'moderated_by', 'moderated_at', 'moderation_comment'),
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data:
            persisted_review = Review.objects.get(pk=obj.pk)
            service = self._moderation_service(obj.status)
            if service:
                service(persisted_review, request.user, comment=obj.moderation_comment)
                return
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    @staticmethod
    def _moderation_service(status):
        return {
            Review.Status.PUBLISHED: ReviewModerationService.publish_review,
            Review.Status.REJECTED: ReviewModerationService.reject_review,
            Review.Status.HIDDEN: ReviewModerationService.hide_review,
        }.get(status)

    @admin.action(description='Опубликовать выбранные отзывы')
    def publish_reviews(self, request, queryset):
        for review in queryset:
            ReviewModerationService.publish_review(review, request.user)

    @admin.action(description='Отклонить выбранные отзывы')
    def reject_reviews(self, request, queryset):
        for review in queryset:
            ReviewModerationService.reject_review(review, request.user)

    @admin.action(description='Скрыть выбранные отзывы')
    def hide_reviews(self, request, queryset):
        for review in queryset:
            ReviewModerationService.hide_review(review, request.user)


@admin.register(Category)
class CategoryAdmin(MPTTModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    ordering = ('tree_id', 'lft')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'logo')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'hex_code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'hex_code')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ('value', 'size_type', 'sort_order', 'is_active')
    list_filter = ('size_type', 'is_active')
    search_fields = ('value',)
    ordering = ('size_type', 'sort_order', 'value')
    list_editable = ('sort_order', 'is_active')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'subtitle', 'link', 'sort_order',
        'is_active', 'created_at', 'updated_at',
    )
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'subtitle', 'link')
    ordering = ('sort_order', 'id')
    list_editable = ('is_active', 'sort_order')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Контент', {
            'fields': ('title', 'subtitle', 'button_text', 'link'),
        }),
        ('Изображения', {
            'fields': ('image', 'image_mobile'),
        }),
        ('Показ', {
            'fields': ('position', 'is_active', 'sort_order', 'starts_at', 'ends_at'),
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


admin.site.register(Promo)

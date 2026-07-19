from django import forms
from django.contrib import admin, messages
from django.db import models
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils.html import format_html
from mptt.admin import MPTTModelAdmin
from .models import (
    Banner, Brand, Category, Color, Product, ProductImage,
    ProductMedia, ProductVariant, Review, Size, StockMovement,
    ImportJob, ImportJobError,
)
from .services import ReviewModerationService


def _is_review_manager(user):
    return bool(
        user
        and user.is_active
        and user.is_staff
        and (
            getattr(user, 'is_superuser', False)
            or getattr(user, 'role', None) in {'manager', 'admin'}
            or user.has_perm('catalog.change_review')
        )
    )


class ReviewAdminForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = '__all__'

    def clean_status(self):
        status = self.cleaned_data['status']
        if not self.instance.pk or status == self.instance.status:
            return status
        if status not in {Review.Status.PUBLISHED, Review.Status.REJECTED, Review.Status.HIDDEN}:
            raise forms.ValidationError('Этот статус нельзя установить из админки.')
        return status


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
    fields = ('media_type', 'file', 'url', 'title_ru', 'title_kz', 'title_en', 'alt_text', 'sort_order', 'is_active', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name_ru', 'name_kz', 'name_en', 'slug', 'category', 'brand',
        'price', 'old_price', 'discount_display',
        'is_new', 'is_sale_display', 'is_active', 'in_stock_display',
        'created_at', 'updated_at',
    )
    list_filter = ('category', 'brand', 'is_active', 'is_new', ProductSaleFilter, ProductStockFilter)
    search_fields = ('name_ru', 'name_kz', 'name_en', 'slug', 'sku', 'variants__sku')
    prepopulated_fields = {'slug': ('name_ru',)}
    list_editable = ('price', 'is_active', 'is_new')
    readonly_fields = (
        'created_at', 'updated_at',
        'views_count', 'orders_count', 'rating', 'reviews_count',
        'discount_display', 'is_sale_display', 'in_stock_display',
    )
    ordering = ('name_ru',)
    inlines = (ProductVariantInline, ProductImageInline, ProductMediaInline)
    fieldsets = (
        ('Основная информация', {
            'fields': (
                'sku', 'name_ru', 'name_kz', 'name_en', 'slug', 'category', 'brand',
                'description_ru', 'description_kz', 'description_en',
                'composition_ru', 'composition_kz', 'composition_en',
                'material_ru', 'material_kz', 'material_en', 'season',
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
    search_fields = ('sku', 'product__name_ru', 'product__name_kz', 'product__name_en', 'product__slug')
    autocomplete_fields = ('product', 'size', 'color')
    ordering = ('product__name_ru', 'sku')
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
    search_fields = ('product__name_ru', 'product__name_kz', 'product__name_en', 'product__slug', 'alt_text')
    autocomplete_fields = ('product',)
    ordering = ('product__name_ru', 'sort_order', 'id')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('variant', 'sku', 'product', 'quantity', 'operation_type', 'user', 'comment', 'created_at')
    list_filter = ('operation_type', 'created_at', 'user')
    search_fields = ('variant__sku', 'variant__product__name_ru', 'variant__product__name_kz', 'variant__product__name_en', 'comment')
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


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status', 'created_by',
        'total_count', 'success_count', 'failed_count',
        'started_at', 'finished_at', 'created_at',
    )
    search_fields = (
        'id',
        'created_by__email',
        'created_by__first_name',
        'created_by__last_name',
        'error_message',
    )
    list_filter = ('status', 'created_at', 'started_at', 'finished_at')
    readonly_fields = (
        'status', 'total_count', 'success_count', 'failed_count',
        'error_message', 'error_report',
        'started_at', 'finished_at', 'created_at', 'updated_at',
    )
    ordering = ('-created_at',)
    autocomplete_fields = ('created_by',)
    fieldsets = (
        ('Файл', {
            'fields': ('file', 'created_by'),
        }),
        ('Статус', {
            'fields': (
                'status', 'total_count', 'success_count', 'failed_count',
                'error_message', 'error_report',
            ),
        }),
        ('Системные поля', {
            'fields': ('started_at', 'finished_at', 'created_at', 'updated_at'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


@admin.register(ImportJobError)
class ImportJobErrorAdmin(admin.ModelAdmin):
    list_display = ('import_job', 'row_number', 'error_message', 'created_at')
    search_fields = ('error_message', 'row_data')
    list_filter = ('created_at',)
    readonly_fields = (
        'import_job', 'row_number', 'row_data',
        'error_message', 'field_errors', 'created_at',
    )
    ordering = ('-created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('import_job')

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
    list_display = ('product', 'media_type', 'title_ru', 'title_kz', 'title_en', 'is_active', 'sort_order')
    list_filter = ('media_type', 'is_active')
    search_fields = (
        'product__name_ru', 'product__name_kz', 'product__name_en',
        'title_ru', 'title_kz', 'title_en', 'url', 'alt_text',
    )
    autocomplete_fields = ('product',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    form = ReviewAdminForm
    list_display = (
        'id', 'product_link', 'user_link', 'order_link', 'rating', 'status', 'short_text',
        'created_at', 'moderated_by', 'moderated_at',
    )
    list_filter = (
        'status', 'rating', 'created_at', 'moderated_at',
    )
    search_fields = (
        'product__name_ru', 'product__name_kz', 'product__name_en', 'product__slug',
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

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'product', 'user', 'order', 'moderated_by',
        )

    def has_module_permission(self, request):
        if _is_review_manager(request.user):
            return True
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if _is_review_manager(request.user):
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if _is_review_manager(request.user):
            return True
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if _is_review_manager(request.user):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if change and 'status' in form.changed_data:
            persisted_review = Review.objects.get(pk=obj.pk)
            service = self._moderation_service(obj.status)
            if service:
                try:
                    service(persisted_review, request.user, comment=obj.moderation_comment)
                except Exception as exc:
                    self.message_user(
                        request,
                        f'Не удалось изменить статус отзыва #{persisted_review.pk}: {exc}',
                        level=messages.ERROR,
                    )
                return
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    @admin.display(description='текст')
    def short_text(self, obj):
        text = obj.text or ''
        if len(text) <= 100:
            return text
        return f'{text[:100]}...'

    @admin.display(description='товар', ordering='product__name_ru')
    def product_link(self, obj):
        url = reverse('admin:catalog_product_change', args=[obj.product_id])
        return format_html('<a href="{}">{}</a>', url, obj.product)

    @admin.display(description='пользователь', ordering='user__email')
    def user_link(self, obj):
        url = reverse('admin:accounts_user_change', args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user)

    @admin.display(description='заказ', ordering='order__created_at')
    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order)

    @staticmethod
    def _moderation_service(status):
        return {
            Review.Status.PUBLISHED: ReviewModerationService.publish_review,
            Review.Status.REJECTED: ReviewModerationService.reject_review,
            Review.Status.HIDDEN: ReviewModerationService.hide_review,
        }.get(status)

    @admin.action(description='Опубликовать выбранные отзывы')
    def publish_reviews(self, request, queryset):
        self._moderate_reviews(request, queryset, ReviewModerationService.publish_review)

    @admin.action(description='Отклонить выбранные отзывы')
    def reject_reviews(self, request, queryset):
        self._moderate_reviews(request, queryset, ReviewModerationService.reject_review)

    @admin.action(description='Скрыть выбранные отзывы')
    def hide_reviews(self, request, queryset):
        self._moderate_reviews(request, queryset, ReviewModerationService.hide_review)

    def _moderate_reviews(self, request, queryset, service):
        moderated = 0
        for review in queryset:
            try:
                service(review, request.user)
            except Exception as exc:
                self.message_user(
                    request,
                    f'Не удалось изменить статус отзыва #{review.pk}: {exc}',
                    level=messages.ERROR,
                )
            else:
                moderated += 1
        if moderated:
            self.message_user(request, f'Обновлено отзывов: {moderated}.', level=messages.SUCCESS)


@admin.register(Category)
class CategoryAdmin(MPTTModelAdmin):
    list_display = ('name_ru', 'name_kz', 'name_en', 'slug', 'parent', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'name_kz', 'name_en', 'slug')
    ordering = ('tree_id', 'lft')
    prepopulated_fields = {'slug': ('name_ru',)}
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'name_kz', 'name_en', 'slug', 'is_active', 'logo')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'name_kz', 'name_en', 'slug')
    ordering = ('name_ru',)
    prepopulated_fields = {'slug': ('name_ru',)}
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'name_kz', 'name_en', 'slug', 'hex_code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'name_kz', 'name_en', 'slug', 'hex_code')
    ordering = ('name_ru',)
    prepopulated_fields = {'slug': ('name_ru',)}
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
        'title_ru', 'title_kz', 'title_en', 'subtitle_ru', 'link', 'sort_order',
        'is_active', 'created_at', 'updated_at',
    )
    list_filter = ('is_active', 'created_at')
    search_fields = (
        'title_ru', 'title_kz', 'title_en',
        'subtitle_ru', 'subtitle_kz', 'subtitle_en', 'link',
    )
    ordering = ('sort_order', 'id')
    list_editable = ('is_active', 'sort_order')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Контент', {
            'fields': (
                'title_ru', 'title_kz', 'title_en',
                'subtitle_ru', 'subtitle_kz', 'subtitle_en',
                'button_text_ru', 'button_text_kz', 'button_text_en', 'link',
            ),
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

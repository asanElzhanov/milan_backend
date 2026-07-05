from django.db import models
from django.db.models import Avg, Count, DecimalField, Exists, F, Min, OuterRef, Q
from django.db.models.functions import Coalesce
import django_filters

from .models import Category, ImportJob, Product, ProductVariant, Review, StockMovement


def with_product_rating_annotations(queryset):
    published_reviews = Q(reviews__status=Review.Status.PUBLISHED)
    return queryset.annotate(
        _average_rating=Avg('reviews__rating', filter=published_reviews),
        _published_reviews_count=Count('reviews', filter=published_reviews, distinct=True),
    )


def with_product_list_annotations(queryset):
    min_variant_price = Min(
        Coalesce(
            'variants__variant_price',
            F('price'),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        filter=Q(variants__is_active=True),
    )
    active_stock_variants = ProductVariant.objects.filter(
        product=OuterRef('pk'),
        is_active=True,
        stock_quantity__gt=0,
    )
    queryset = queryset.annotate(
        _min_variant_price=min_variant_price,
    ).annotate(
        _min_price=Coalesce(
            '_min_variant_price',
            F('price'),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
    ).annotate(
        _in_stock=Exists(active_stock_variants),
    )
    return with_product_rating_annotations(queryset)


class ProductFilter(django_filters.FilterSet):
    price_from = django_filters.NumberFilter(method='filter_min_price_gte')
    price_to = django_filters.NumberFilter(method='filter_min_price_lte')
    price_min = django_filters.NumberFilter(method='filter_min_price_gte')
    price_max = django_filters.NumberFilter(method='filter_min_price_lte')
    min_price = django_filters.NumberFilter(method='filter_min_price_gte')
    max_price = django_filters.NumberFilter(method='filter_min_price_lte')
    brand = django_filters.CharFilter(method='filter_brand')
    brand_slug = django_filters.CharFilter(method='filter_brand')
    category = django_filters.CharFilter(method='filter_category')
    category_slug = django_filters.CharFilter(method='filter_category')
    subcategory = django_filters.CharFilter(method='filter_category')
    subcategory_slug = django_filters.CharFilter(method='filter_category')
    color = django_filters.CharFilter(method='filter_color')
    size = django_filters.CharFilter(method='filter_size')
    material = django_filters.CharFilter(field_name='material', lookup_expr='icontains')
    season = django_filters.CharFilter(field_name='season')
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    is_sale = django_filters.BooleanFilter(method='filter_is_sale')
    has_discount = django_filters.BooleanFilter(method='filter_has_discount')
    is_new = django_filters.BooleanFilter(field_name='is_new')

    class Meta:
        model = Product
        fields = [
            'price_from', 'price_to',
            'price_min', 'price_max', 'min_price', 'max_price',
            'brand', 'brand_slug',
            'category', 'category_slug', 'subcategory', 'subcategory_slug',
            'color', 'size', 'material', 'season',
            'in_stock', 'has_discount', 'is_sale', 'is_new',
        ]

    def filter_min_price_gte(self, queryset, name, value):
        return with_product_list_annotations(queryset).filter(_min_price__gte=value)

    def filter_min_price_lte(self, queryset, name, value):
        return with_product_list_annotations(queryset).filter(_min_price__lte=value)

    def filter_brand(self, queryset, name, value):
        values = self._get_multiple_values(name, value)
        brand_filter = Q()
        for item in values:
            if item.isdigit():
                brand_filter |= Q(brand_id=item)
            else:
                brand_filter |= Q(brand__slug=item)
        return queryset.filter(brand_filter)

    def filter_category(self, queryset, name, value):
        category_queryset = Category.objects.all()
        if value.isdigit():
            category = category_queryset.filter(pk=value).first()
        else:
            category = category_queryset.filter(slug=value).first()

        if category is None:
            return queryset.none()

        category_ids = category.get_descendants(include_self=True).values('pk')
        return queryset.filter(category_id__in=category_ids)

    def filter_color(self, queryset, name, value):
        values = self._get_multiple_values(name, value)
        variants = ProductVariant.objects.filter(
            product=OuterRef('pk'),
            is_active=True,
        )
        color_filter = Q()
        for item in values:
            if item.isdigit():
                color_filter |= Q(color_id=item)
            else:
                color_filter |= Q(color__slug=item)
        variants = variants.filter(color_filter)
        return queryset.filter(Exists(variants))

    def filter_size(self, queryset, name, value):
        values = self._get_multiple_values(name, value)
        variants = ProductVariant.objects.filter(
            product=OuterRef('pk'),
            is_active=True,
        )
        size_filter = Q()
        for item in values:
            if item.isdigit():
                size_filter |= Q(size_id=item) | Q(size__value=item)
            else:
                size_filter |= Q(size__value=item)
        variants = variants.filter(size_filter)
        return queryset.filter(Exists(variants))

    def _get_multiple_values(self, name, value):
        """Accept both repeated query params and comma-separated values."""
        raw_values = self.data.getlist(name) if hasattr(self.data, 'getlist') else [value]
        return [
            item.strip()
            for raw_value in raw_values
            for item in str(raw_value).split(',')
            if item.strip()
        ]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return with_product_list_annotations(queryset).filter(_in_stock=True)
        return with_product_list_annotations(queryset).filter(_in_stock=False)

    def filter_is_sale(self, queryset, name, value):
        if value:
            return queryset.filter(old_price__isnull=False, old_price__gt=models.F('price'))
        return queryset.filter(
            models.Q(old_price__isnull=True)
            | models.Q(old_price__lte=models.F('price'))
        )

    def filter_has_discount(self, queryset, name, value):
        return self.filter_is_sale(queryset, name, value)


class StockVariantFilter(django_filters.FilterSet):
    product = django_filters.CharFilter(method='filter_product')
    product_slug = django_filters.CharFilter(field_name='product__slug')
    category = django_filters.CharFilter(method='filter_category')
    category_slug = django_filters.CharFilter(field_name='product__category__slug')
    brand = django_filters.CharFilter(method='filter_brand')
    brand_slug = django_filters.CharFilter(field_name='product__brand__slug')
    size = django_filters.CharFilter(method='filter_size')
    color = django_filters.CharFilter(method='filter_color')
    sku = django_filters.CharFilter(field_name='sku', lookup_expr='icontains')
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    is_active = django_filters.BooleanFilter(field_name='is_active')

    class Meta:
        model = ProductVariant
        fields = [
            'product', 'product_slug', 'category', 'category_slug',
            'brand', 'brand_slug', 'size', 'color', 'sku',
            'in_stock', 'is_active',
        ]

    def filter_product(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(product_id=value)
        return queryset.filter(product__slug=value)

    def filter_category(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(product__category_id=value)
        return queryset.filter(product__category__slug=value)

    def filter_brand(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(product__brand_id=value)
        return queryset.filter(product__brand__slug=value)

    def filter_size(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(size_id=value)
        return queryset.filter(size__value=value)

    def filter_color(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(color_id=value)
        return queryset.filter(color__slug=value)

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(is_active=True, stock_quantity__gt=0)
        return queryset.filter(models.Q(is_active=False) | models.Q(stock_quantity=0))


class StockMovementFilter(django_filters.FilterSet):
    variant = django_filters.NumberFilter(field_name='variant_id')
    product = django_filters.CharFilter(method='filter_product')
    sku = django_filters.CharFilter(field_name='variant__sku', lookup_expr='icontains')
    operation_type = django_filters.CharFilter(field_name='operation_type')
    user = django_filters.NumberFilter(field_name='user_id')
    date_from = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = StockMovement
        fields = ['variant', 'product', 'sku', 'operation_type', 'user', 'date_from', 'date_to']

    def filter_product(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(variant__product_id=value)
        return queryset.filter(variant__product__slug=value)


class ImportJobFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name='status')
    created_by = django_filters.NumberFilter(field_name='created_by_id')
    date_from = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = ImportJob
        fields = ['status', 'created_by', 'date_from', 'date_to']

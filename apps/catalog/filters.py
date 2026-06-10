from django.db import models
from django.db.models import DecimalField, Exists, F, Min, OuterRef, Q
from django.db.models.functions import Coalesce
import django_filters

from .models import Product, ProductVariant


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
    return queryset.annotate(
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


class ProductFilter(django_filters.FilterSet):
    price_min = django_filters.NumberFilter(method='filter_min_price_gte')
    price_max = django_filters.NumberFilter(method='filter_min_price_lte')
    min_price = django_filters.NumberFilter(method='filter_min_price_gte')
    max_price = django_filters.NumberFilter(method='filter_min_price_lte')
    brand = django_filters.CharFilter(method='filter_brand')
    brand_slug = django_filters.CharFilter(field_name='brand__slug')
    category = django_filters.CharFilter(method='filter_category')
    category_slug = django_filters.CharFilter(field_name='category__slug')
    color = django_filters.CharFilter(field_name='variants__color__id')
    size = django_filters.CharFilter(field_name='variants__size__value')
    material = django_filters.CharFilter(field_name='material', lookup_expr='icontains')
    season = django_filters.CharFilter(field_name='season')
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    is_sale = django_filters.BooleanFilter(method='filter_is_sale')
    has_discount = django_filters.BooleanFilter(method='filter_has_discount')
    is_new = django_filters.BooleanFilter(field_name='is_new')

    class Meta:
        model = Product
        fields = [
            'price_min', 'price_max', 'min_price', 'max_price',
            'brand', 'brand_slug', 'category', 'category_slug',
            'color', 'size', 'material', 'season',
            'in_stock', 'has_discount', 'is_sale', 'is_new',
        ]

    def filter_min_price_gte(self, queryset, name, value):
        return with_product_list_annotations(queryset).filter(_min_price__gte=value)

    def filter_min_price_lte(self, queryset, name, value):
        return with_product_list_annotations(queryset).filter(_min_price__lte=value)

    def filter_brand(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(brand_id=value)
        return queryset.filter(brand__slug=value)

    def filter_category(self, queryset, name, value):
        if value.isdigit():
            return queryset.filter(category_id=value)
        return queryset.filter(category__slug=value)

    def filter_in_stock(self, queryset, name, value):
        if value:
            return with_product_list_annotations(queryset).filter(_in_stock=True)
        return with_product_list_annotations(queryset).filter(_in_stock=False)

    def filter_is_sale(self, queryset, name, value):
        if value:
            return queryset.filter(old_price__isnull=False, old_price__gt=models.F('price'))
        return queryset.filter(models.Q(old_price__isnull=True) | models.Q(old_price__lte=models.F('price')))

    def filter_has_discount(self, queryset, name, value):
        return self.filter_is_sale(queryset, name, value)

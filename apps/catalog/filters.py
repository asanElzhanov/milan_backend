from django.db import models
import django_filters

from .models import Product


class ProductFilter(django_filters.FilterSet):
    price_min = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    price_max = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    brand = django_filters.CharFilter(field_name='brand__slug')
    category = django_filters.CharFilter(field_name='category__slug')
    color = django_filters.CharFilter(field_name='variants__color__id')
    size = django_filters.CharFilter(field_name='variants__size__value')
    material = django_filters.CharFilter(field_name='material', lookup_expr='icontains')
    season = django_filters.CharFilter(field_name='season')
    in_stock = django_filters.BooleanFilter(method='filter_in_stock')
    has_discount = django_filters.BooleanFilter(method='filter_has_discount')
    is_new = django_filters.BooleanFilter(field_name='is_new')

    class Meta:
        model = Product
        fields = [
            'price_min', 'price_max', 'brand', 'category',
            'color', 'size', 'material', 'season',
            'in_stock', 'has_discount', 'is_new',
        ]

    def filter_in_stock(self, queryset, name, value):
        if value:
            return queryset.filter(variants__stock__gt=0).distinct()
        return queryset

    def filter_has_discount(self, queryset, name, value):
        if value:
            return queryset.filter(old_price__isnull=False, old_price__gt=models.F('price'))
        return queryset

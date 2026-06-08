from rest_framework import generics, filters, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import F
from django.utils import timezone

from .models import Category, Brand, Product, Review, Banner, Promo
from .serializers import (
    CategorySerializer, BrandSerializer,
    ProductListSerializer, ProductDetailSerializer,
    ReviewSerializer, ReviewCreateSerializer,
    BannerSerializer, PromoCheckSerializer,
)
from .filters import ProductFilter


class CategoryListView(generics.ListAPIView):
    """GET /catalog/categories/ — дерево категорий (только корневые с детьми)"""
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Category.objects.filter(is_active=True, level=0).prefetch_related('children')


class BrandListView(generics.ListAPIView):
    """GET /catalog/brands/"""
    serializer_class = BrandSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Brand.objects.filter(is_active=True)


class ProductListView(generics.ListAPIView):
    """GET /catalog/products/?category=krossovki&brand=nike&price_min=10000"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'description', 'brand__name', 'sku']
    ordering_fields = ['price', 'created_at', 'rating', 'orders_count', 'discount_percent']
    ordering = ['-created_at']

    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related(
            'category', 'brand'
        ).prefetch_related('images').distinct()


class ProductDetailView(generics.RetrieveAPIView):
    """GET /catalog/products/<slug>/"""
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return Product.objects.filter(is_active=True).select_related(
            'category', 'brand'
        ).prefetch_related('images', 'videos', 'variants__color', 'variants__size', 'reviews__user')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Инкремент просмотров без race condition
        Product.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class ProductSimilarView(generics.ListAPIView):
    """GET /catalog/products/<slug>/similar/"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        product = Product.objects.get(slug=self.kwargs['slug'])
        return Product.objects.filter(
            category=product.category, is_active=True
        ).exclude(pk=product.pk).order_by('-orders_count')[:8]


class ReviewListCreateView(generics.ListCreateAPIView):
    """GET/POST /catalog/products/<slug>/reviews/"""

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ReviewCreateSerializer
        return ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(
            product__slug=self.kwargs['slug'],
            is_approved=True
        ).select_related('user').prefetch_related('images')

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['product'] = Product.objects.get(slug=self.kwargs['slug'])
        return ctx

    def perform_create(self, serializer):
        review = serializer.save()
        self._update_product_rating(review.product)

    def _update_product_rating(self, product):
        reviews = Review.objects.filter(product=product, is_approved=True)
        count = reviews.count()
        if count > 0:
            avg = sum(r.rating for r in reviews) / count
            product.rating = round(avg, 2)
            product.reviews_count = count
            product.save(update_fields=['rating', 'reviews_count'])


class BannerListView(generics.ListAPIView):
    """GET /catalog/banners/?position=hero"""
    serializer_class = BannerSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        now = timezone.now()
        qs = Banner.objects.filter(is_active=True)
        position = self.request.query_params.get('position')
        if position:
            qs = qs.filter(position=position)
        return qs.filter(
            models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now),
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now),
        )


class PromoCheckView(APIView):
    """POST /catalog/promo/check/ — проверить промокод"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PromoCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        promo = serializer.validated_data['promo']
        amount = serializer.validated_data['order_amount']
        discount = promo.calculate_discount(amount)
        return Response({
            'code': promo.code,
            'discount_type': promo.discount_type,
            'discount_value': str(promo.discount_value),
            'discount_amount': str(discount),
            'final_amount': str(amount - discount),
        })


# Fix missing import
from django.db import models

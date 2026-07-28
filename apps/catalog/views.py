from django.db import models
from django.db.models import F, Prefetch
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import filters, generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsManagerOrAdmin
from apps.orders.services import PromoCodeService

from .models import (
    Banner, Brand, Category, Color, Product, ProductImage,
    ProductMedia, ProductVariant, Review, Size, StockMovement,
    ImportJob, ImportJobError,
)
from .serializers import (
    CategorySerializer, CategoryTreeSerializer, BrandSerializer, ColorSerializer, SizeSerializer,
    ProductListSerializer, ProductDetailSerializer,
    ReviewSerializer, ReviewCreateSerializer, ReviewListSerializer,
    BannerSerializer, PromoCheckSerializer,
    StockAdjustmentSerializer, StockMovementSerializer, StockVariantSerializer,
    ImportJobUploadSerializer, ImportJobListSerializer, ImportJobDetailSerializer,
    ImportJobErrorSerializer,
)
from .tasks import schedule_product_import
from .services import InvalidStockQuantityError, StockService
from .filters import (
    ImportJobFilter, ProductFilter, StockMovementFilter, StockVariantFilter,
    with_product_list_annotations, with_product_rating_annotations,
)


def _parse_bool(value):
    if value is None:
        return None
    value = value.lower()
    if value in {'1', 'true', 'yes', 'y'}:
        return True
    if value in {'0', 'false', 'no', 'n'}:
        return False
    return None


class CategoryQuerysetMixin:
    def get_active_filter(self):
        return _parse_bool(self.request.query_params.get('active'))

    def get_queryset(self):
        queryset = Category.objects.all()

        active = self.get_active_filter()
        if active is True:
            queryset = queryset.active()
        elif active is False:
            queryset = queryset.filter(is_active=False)

        parent = self.request.query_params.get('parent')
        if parent:
            queryset = queryset.filter(parent_id=parent)

        return queryset.order_by('tree_id', 'lft')


class ActiveFilterMixin:
    def filter_by_active(self, queryset):
        active = _parse_bool(self.request.query_params.get('active'))
        if active is True:
            return queryset.filter(is_active=True)
        if active is False:
            return queryset.filter(is_active=False)
        return queryset


class ProductOrderingFilter(filters.OrderingFilter):
    ordering_aliases = {
        'price': '_min_price',
        'min_price': '_min_price',
    }

    def get_ordering(self, request, queryset, view):
        ordering = request.query_params.get(self.ordering_param)
        if ordering is None:
            ordering = request.query_params.get('sort')
        if ordering:
            fields = [field.strip() for field in ordering.split(',')]
            ordering = self.remove_invalid_fields(queryset, fields, view, request)
            if ordering:
                return ordering
        return self.get_default_ordering(view)

    def remove_invalid_fields(self, queryset, fields, view, request):
        valid_fields = super().remove_invalid_fields(queryset, fields, view, request)
        ordering = []
        for field in valid_fields:
            prefix = '-' if field.startswith('-') else ''
            field_name = field[1:] if prefix else field
            ordering.append(f'{prefix}{self.ordering_aliases.get(field_name, field_name)}')
        return ordering


class CategoryListView(CategoryQuerysetMixin, generics.ListAPIView):
    """GET /catalog/categories/?active=true&parent=1 — плоский список категорий"""
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Catalog / Categories'],
        summary='Плоский список категорий',
        parameters=[
            OpenApiParameter('active', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter('parent', OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: CategorySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CategoryTreeView(CategoryQuerysetMixin, generics.ListAPIView):
    """GET /catalog/categories/tree/?active=true — дерево категорий"""
    serializer_class = CategoryTreeSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return super().get_queryset().filter(level=0).prefetch_related('children')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['active'] = self.get_active_filter()
        return context

    @extend_schema(
        tags=['Catalog / Categories'],
        summary='Дерево категорий',
        parameters=[
            OpenApiParameter('active', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
        ],
        responses={200: CategoryTreeSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CategoryDetailView(CategoryQuerysetMixin, generics.RetrieveAPIView):
    """GET /catalog/categories/<slug>/"""
    serializer_class = CategoryTreeSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return Category.objects.active().order_by('tree_id', 'lft')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['active'] = True
        return context

    @extend_schema(
        tags=['Catalog / Categories'],
        summary='Категория по slug',
        responses={200: CategoryTreeSerializer, 404: OpenApiResponse(description='Категория не найдена')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BrandListView(ActiveFilterMixin, generics.ListAPIView):
    """GET /catalog/brands/?active=true"""
    serializer_class = BrandSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = self.filter_by_active(Brand.objects.all())
        return queryset.order_by('name_ru')

    @extend_schema(
        tags=['Catalog / Brands'],
        summary='Список брендов',
        parameters=[OpenApiParameter('active', OpenApiTypes.BOOL, OpenApiParameter.QUERY)],
        responses={200: BrandSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BrandDetailView(generics.RetrieveAPIView):
    """GET /catalog/brands/<slug>/"""
    serializer_class = BrandSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'
    queryset = Brand.objects.filter(is_active=True)

    @extend_schema(
        tags=['Catalog / Brands'],
        summary='Бренд по slug',
        responses={200: BrandSerializer, 404: OpenApiResponse(description='Бренд не найден')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ColorListView(ActiveFilterMixin, generics.ListAPIView):
    """GET /catalog/colors/?active=true"""
    serializer_class = ColorSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = self.filter_by_active(Color.objects.all())
        return queryset.order_by('name_ru')

    @extend_schema(
        tags=['Catalog / Colors'],
        summary='Список цветов',
        parameters=[OpenApiParameter('active', OpenApiTypes.BOOL, OpenApiParameter.QUERY)],
        responses={200: ColorSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class SizeListView(ActiveFilterMixin, generics.ListAPIView):
    """GET /catalog/sizes/?active=true&size_type=shoes"""
    serializer_class = SizeSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = self.filter_by_active(Size.objects.all())

        size_type = self.request.query_params.get('size_type')
        if size_type:
            queryset = queryset.filter(size_type=size_type)

        return queryset.order_by('size_type', 'sort_order', 'value')

    @extend_schema(
        tags=['Catalog / Sizes'],
        summary='Список размеров',
        parameters=[
            OpenApiParameter('active', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter(
                'size_type',
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                enum=[choice[0] for choice in Size.SizeType.choices],
            ),
        ],
        responses={200: SizeSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductListView(generics.ListAPIView):
    """GET /catalog/products/?category=krossovki&brand=nike&price_from=10000"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, ProductOrderingFilter]
    filterset_class = ProductFilter
    search_fields = [
        'name_ru', 'name_kz', 'name_en',
        'brand__name_ru', 'brand__name_kz', 'brand__name_en', 'variants__sku',
    ]
    ordering_fields = ['price', 'created_at', 'name_ru']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = with_product_list_annotations(
            Product.objects.filter(is_active=True).select_related('category', 'brand')
        )
        return queryset.prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.order_by('sort_order', 'id')),
            Prefetch(
                'variants',
                queryset=ProductVariant.objects.filter(is_active=True).select_related('color', 'size'),
            ),
        ).distinct()

    @extend_schema(
        tags=['Catalog / Products'],
        summary='Список товаров',
        parameters=[
            OpenApiParameter('category', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('category_slug', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('subcategory', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('subcategory_slug', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('brand', OpenApiTypes.STR, OpenApiParameter.QUERY, many=True),
            OpenApiParameter('brand_slug', OpenApiTypes.STR, OpenApiParameter.QUERY, many=True),
            OpenApiParameter('color', OpenApiTypes.STR, OpenApiParameter.QUERY, many=True),
            OpenApiParameter('size', OpenApiTypes.STR, OpenApiParameter.QUERY, many=True),
            OpenApiParameter('price_from', OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter('price_to', OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter('price_min', OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter('price_max', OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter('in_stock', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter('is_sale', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter('is_new', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter('search', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('ordering', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('sort', OpenApiTypes.STR, OpenApiParameter.QUERY),
        ],
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductDetailView(generics.RetrieveAPIView):
    """GET /catalog/products/<slug>/"""
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True).select_related(
            'category', 'brand'
        )
        queryset = with_product_rating_annotations(queryset)
        return queryset.prefetch_related(
            Prefetch('images', queryset=ProductImage.objects.order_by('sort_order', 'id')),
            Prefetch(
                'media',
                queryset=ProductMedia.objects.filter(is_active=True).order_by('sort_order', 'id'),
                to_attr='active_media',
            ),
            'videos',
            Prefetch(
                'variants',
                queryset=ProductVariant.objects.select_related(
                    'product', 'color', 'size',
                ).order_by('id'),
            ),
            Prefetch(
                'reviews',
                queryset=Review.objects.filter(status=Review.Status.PUBLISHED)
                .select_related('user')
                .prefetch_related('images')
                .order_by('-created_at'),
                to_attr='approved_reviews',
            ),
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Инкремент просмотров без race condition
        Product.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @extend_schema(
        tags=['Catalog / Products'],
        summary='Карточка товара',
        responses={200: ProductDetailSerializer, 404: OpenApiResponse(description='Товар не найден')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class StockVariantListView(generics.ListAPIView):
    """GET /catalog/stock/ — остатки по вариантам товаров"""
    serializer_class = StockVariantSerializer
    permission_classes = [IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StockVariantFilter
    search_fields = [
        'sku', 'product__name_ru', 'product__name_kz', 'product__name_en', 'product__slug',
    ]
    ordering_fields = ['stock_quantity', 'sku', 'product__name_ru']
    ordering = ['product__name_ru', 'sku']

    def get_queryset(self):
        return ProductVariant.objects.select_related(
            'product__category', 'product__brand', 'size', 'color',
        )

    @extend_schema(
        tags=['Catalog / Stock'],
        summary='Список остатков по вариантам',
        parameters=[
            OpenApiParameter('product', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('product_slug', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('category', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('category_slug', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('brand', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('brand_slug', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('size', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('color', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('sku', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('in_stock', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
            OpenApiParameter('is_active', OpenApiTypes.BOOL, OpenApiParameter.QUERY),
        ],
        responses={200: StockVariantSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class StockMovementListView(generics.ListAPIView):
    """GET /catalog/stock/movements/ — история движений склада"""
    serializer_class = StockMovementSerializer
    permission_classes = [IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StockMovementFilter
    search_fields = [
        'variant__sku',
        'variant__product__name_ru', 'variant__product__name_kz', 'variant__product__name_en',
        'variant__product__slug', 'comment',
    ]
    ordering_fields = ['created_at', 'operation_type', 'quantity']
    ordering = ['-created_at']

    def get_queryset(self):
        return StockMovement.objects.select_related(
            'variant__product__category',
            'variant__product__brand',
            'variant__size',
            'variant__color',
            'user',
        )

    @extend_schema(
        tags=['Catalog / Stock'],
        summary='История движений склада',
        parameters=[
            OpenApiParameter('variant', OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter('product', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('sku', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('operation_type', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('user', OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter('date_from', OpenApiTypes.DATETIME, OpenApiParameter.QUERY),
            OpenApiParameter('date_to', OpenApiTypes.DATETIME, OpenApiParameter.QUERY),
        ],
        responses={200: StockMovementSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class StockAdjustmentView(APIView):
    """POST /catalog/stock/adjust/ — ручная корректировка остатка для фронта"""
    permission_classes = [IsManagerOrAdmin]

    @extend_schema(
        tags=['Catalog / Stock'],
        summary='Ручная корректировка остатка',
        request=StockAdjustmentSerializer,
        responses={
            201: StockMovementSerializer,
            400: OpenApiResponse(description='Ошибка корректировки остатка'),
            404: OpenApiResponse(description='Вариант товара не найден'),
        },
    )
    def post(self, request):
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variant_id = serializer.validated_data['variant_id']
        new_quantity = serializer.validated_data['new_quantity']
        comment = serializer.validated_data.get('comment', '').strip()
        if not comment:
            comment = f'Manual adjustment to {new_quantity} via API'

        try:
            movement = StockService.manual_adjustment(
                variant=variant_id,
                new_quantity=new_quantity,
                user=request.user,
                comment=comment,
            )
        except ProductVariant.DoesNotExist:
            return Response({'detail': 'Вариант товара не найден.'}, status=status.HTTP_404_NOT_FOUND)
        except InvalidStockQuantityError as exc:
            detail = exc.messages[0] if hasattr(exc, 'messages') else str(exc)
            return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)

        movement = StockMovement.objects.select_related(
            'variant__product',
            'user',
        ).get(pk=movement.pk)
        return Response(
            StockMovementSerializer(movement, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProductImportJobListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsManagerOrAdmin]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = ImportJobFilter
    ordering_fields = ['created_at', 'started_at', 'finished_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return ImportJob.objects.select_related('created_by').order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ImportJobUploadSerializer
        return ImportJobListSerializer

    @extend_schema(
        tags=['Catalog / Imports'],
        summary='История импортов товаров',
        parameters=[
            OpenApiParameter('status', OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter('created_by', OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter('date_from', OpenApiTypes.DATETIME, OpenApiParameter.QUERY),
            OpenApiParameter('date_to', OpenApiTypes.DATETIME, OpenApiParameter.QUERY),
            OpenApiParameter('ordering', OpenApiTypes.STR, OpenApiParameter.QUERY),
        ],
        responses={200: ImportJobListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['Catalog / Imports'],
        summary='Загрузить CSV импорт товаров',
        request=ImportJobUploadSerializer,
        responses={
            202: ImportJobListSerializer,
            400: OpenApiResponse(description='Ошибка валидации файла'),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            import_job = serializer.save(created_by=request.user)
            schedule_product_import(import_job.id)
        import_job = ImportJob.objects.select_related('created_by').get(pk=import_job.pk)
        return Response(
            ImportJobListSerializer(import_job, context=self.get_serializer_context()).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ProductImportJobDetailView(generics.RetrieveAPIView):
    serializer_class = ImportJobDetailSerializer
    permission_classes = [IsManagerOrAdmin]

    def get_queryset(self):
        return ImportJob.objects.select_related('created_by')

    @extend_schema(
        tags=['Catalog / Imports'],
        summary='Детали импорта товаров',
        responses={200: ImportJobDetailSerializer, 404: OpenApiResponse(description='Импорт не найден')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductImportJobErrorListView(generics.ListAPIView):
    serializer_class = ImportJobErrorSerializer
    permission_classes = [IsManagerOrAdmin]
    ordering = ['row_number']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ImportJobError.objects.none()
        get_object_or_404(ImportJob, pk=self.kwargs['pk'])
        return ImportJobError.objects.filter(
            import_job_id=self.kwargs['pk'],
        ).order_by('row_number', 'id')

    @extend_schema(
        tags=['Catalog / Imports'],
        summary='Ошибки строк импорта товаров',
        responses={200: ImportJobErrorSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductImportJobErrorReportView(APIView):
    permission_classes = [IsManagerOrAdmin]

    @extend_schema(
        tags=['Catalog / Imports'],
        summary='Скачать CSV отчёт ошибок импорта товаров',
        responses={
            200: OpenApiTypes.BINARY,
            404: OpenApiResponse(description='Отчёт не найден'),
        },
    )
    def get(self, request, pk):
        import_job = get_object_or_404(ImportJob, pk=pk)
        report = import_job.error_report or {}
        report_path = report.get('file') if isinstance(report, dict) else None
        if not report_path:
            raise Http404('Отчёт ошибок не найден.')

        storage = import_job.file.storage
        if not storage.exists(report_path):
            raise Http404('Файл отчёта ошибок не найден.')

        filename = report_path.rsplit('/', 1)[-1]
        return FileResponse(
            storage.open(report_path, 'rb'),
            as_attachment=True,
            filename=filename,
            content_type='text/csv',
        )


class ProductSimilarView(generics.ListAPIView):
    """GET /catalog/products/<slug>/similar/"""
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Product.objects.none()
        from apps.recommendations.constants import RecommendationContext
        from apps.recommendations.services import ProductEligibilityService, RecommendationService

        product = get_object_or_404(
            Product.objects.filter(is_active=True),
            slug=self.kwargs['slug'],
        )
        product_ids = RecommendationService.similar_product_ids(product, limit=8)
        return ProductEligibilityService.hydrate(
            product_ids,
            context=RecommendationContext.PRODUCT,
            exclude_ids={product.id},
        )

    @extend_schema(
        tags=['Catalog / Products'],
        summary='Похожие товары',
        responses={200: ProductListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProductReviewListView(generics.ListAPIView):
    """GET /catalog/products/<slug>/reviews/"""
    serializer_class = ReviewListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Review.objects.none()
        return Review.objects.filter(
            product__slug=self.kwargs['slug'],
            status=Review.Status.PUBLISHED,
        ).select_related('user', 'product', 'order').prefetch_related('images').order_by('-created_at')

    @extend_schema(
        tags=['Catalog / Reviews'],
        summary='Отзывы товара',
        responses={200: ReviewListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReviewCreateView(generics.CreateAPIView):
    """POST /catalog/reviews/"""
    serializer_class = ReviewCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return Review.objects.select_related('product', 'user', 'order').prefetch_related('images')

    @extend_schema(
        tags=['Catalog / Reviews'],
        summary='Создать отзыв',
        request=ReviewCreateSerializer,
        responses={201: ReviewSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save()
        review = self.get_queryset().get(pk=review.pk)
        response_serializer = ReviewSerializer(review, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class MyReviewListView(generics.ListAPIView):
    """GET /catalog/reviews/mine/"""
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Review.objects.none()
        return (
            Review.objects.filter(user=self.request.user)
            .select_related('product', 'user', 'order')
            .prefetch_related('images')
            .order_by('-created_at')
        )

    @extend_schema(
        tags=['Catalog / Reviews'],
        summary='Мои отзывы',
        responses={200: ReviewSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


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
        ).order_by('sort_order', 'id')

    @extend_schema(
        tags=['Catalog / Marketing'],
        summary='Список баннеров',
        parameters=[OpenApiParameter('position', OpenApiTypes.STR, OpenApiParameter.QUERY)],
        responses={200: BannerSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PromoCheckView(APIView):
    """POST /catalog/promo/check/ — проверить промокод"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Catalog / Marketing'],
        summary='Проверить промокод',
        request=PromoCheckSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiResponse(description='Промокод недействителен')},
    )
    def post(self, request):
        serializer = PromoCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        promo_code = serializer.validated_data['promo_code']
        amount = serializer.validated_data['order_amount']
        discount = PromoCodeService.calculate_discount(promo_code, amount)
        return Response({
            'code': promo_code.code,
            'discount_type': promo_code.discount_type,
            'discount_value': str(promo_code.value),
            'discount_amount': str(discount),
            'final_amount': str(amount - discount),
        })

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.urls import reverse
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from apps.orders.models import Order

from .models import (
    Banner, Brand, Category, Color, Product, ProductImage,
    ProductMedia, ProductVariant, Promo, Review, ReviewImage, Size, StockMovement,
    ImportJob, ImportJobError,
)
from .services import ProductReviewService


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            'id', 'name', 'slug', 'parent', 'image', 'description',
            'is_active', 'sort_order', 'seo_title', 'seo_description',
            'seo_keywords',
        )


class CategoryTreeSerializer(CategorySerializer):
    children = serializers.SerializerMethodField()

    class Meta(CategorySerializer.Meta):
        fields = CategorySerializer.Meta.fields + ('children',)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_children(self, obj):
        children = obj.children.all()
        active = self.context.get('active')
        if active is not None:
            children = children.filter(is_active=active)
        return CategoryTreeSerializer(children, many=True, context=self.context).data


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ('id', 'name', 'slug', 'logo', 'is_active')


class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ('id', 'name', 'slug', 'hex_code', 'is_active')


class SizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ('id', 'value', 'size_type', 'sort_order', 'is_active')


class ProductImageSerializer(serializers.ModelSerializer):
    alt = serializers.CharField(source='alt_text', read_only=True)

    class Meta:
        model = ProductImage
        fields = (
            'id', 'image', 'alt_text', 'alt',
            'is_main', 'sort_order', 'created_at', 'updated_at',
        )


class ProductMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMedia
        fields = (
            'id', 'media_type', 'file', 'url', 'title', 'alt_text',
            'sort_order', 'is_active', 'created_at', 'updated_at',
        )


class ProductVariantSerializer(serializers.ModelSerializer):
    color = ColorSerializer()
    size = SizeSerializer()
    active = serializers.BooleanField(source='is_active', read_only=True)
    stock = serializers.IntegerField(source='stock_quantity', read_only=True)
    sku_variant = serializers.CharField(source='sku', read_only=True)
    extra_price = serializers.SerializerMethodField()
    effective_price = serializers.ReadOnlyField(source='final_price')
    in_stock = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()
    final_price = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = (
            'id', 'color', 'size',
            'sku', 'stock_quantity', 'variant_price', 'active', 'is_active',
            'stock', 'sku_variant', 'extra_price',
            'effective_price', 'in_stock', 'is_available', 'final_price',
        )

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_extra_price(self, obj):
        if obj.variant_price is None:
            return '0.00'
        return str(obj.variant_price - obj.product.price)


class StockVariantSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(source='id', read_only=True)
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    category = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    size = SizeSerializer(read_only=True)
    color = ColorSerializer(read_only=True)
    in_stock = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = (
            'variant_id', 'product_id', 'product_name', 'product_slug',
            'category', 'brand', 'size', 'color',
            'sku', 'stock_quantity', 'is_active', 'in_stock',
        )

    @extend_schema_field(serializers.DictField())
    def get_category(self, obj):
        category = obj.product.category
        if not category:
            return None
        return {'id': category.id, 'name': category.name, 'slug': category.slug}

    @extend_schema_field(serializers.DictField())
    def get_brand(self, obj):
        brand = obj.product.brand
        if not brand:
            return None
        return {'id': brand.id, 'name': brand.name, 'slug': brand.slug}


class StockMovementSerializer(serializers.ModelSerializer):
    variant = serializers.IntegerField(source='variant_id', read_only=True)
    product = serializers.SerializerMethodField()
    sku = serializers.CharField(source='variant.sku', read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = (
            'id', 'variant', 'product', 'sku',
            'quantity', 'operation_type', 'user', 'comment', 'created_at',
        )

    @extend_schema_field(serializers.DictField())
    def get_product(self, obj):
        product = obj.variant.product
        return {'id': product.id, 'name': product.name, 'slug': product.slug}

    @extend_schema_field(serializers.DictField())
    def get_user(self, obj):
        if not obj.user:
            return None
        return {
            'id': obj.user.id,
            'email': obj.user.email,
            'full_name': obj.user.full_name,
        }


class StockAdjustmentSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    new_quantity = serializers.IntegerField(min_value=0)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ImportJobUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=True)

    class Meta:
        model = ImportJob
        fields = ('file',)

    def validate_file(self, value):
        filename = getattr(value, 'name', '')
        if not filename.lower().endswith('.csv'):
            raise serializers.ValidationError('Загрузите CSV файл с расширением .csv.')

        content_type = getattr(value, 'content_type', '')
        allowed_content_types = {
            '',
            'text/csv',
            'application/csv',
            'application/vnd.ms-excel',
            'text/plain',
            'application/octet-stream',
        }
        if content_type not in allowed_content_types:
            raise serializers.ValidationError('Файл должен быть в формате CSV.')
        return value


class ImportJobBaseSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    error_report = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = (
            'id', 'status', 'total_count', 'success_count', 'failed_count',
            'error_message', 'error_report', 'created_by',
            'started_at', 'finished_at', 'created_at',
        )

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_created_by(self, obj):
        if not obj.created_by:
            return None
        return {
            'id': obj.created_by_id,
            'email': obj.created_by.email,
            'full_name': obj.created_by.full_name,
        }

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_error_report(self, obj):
        report = obj.error_report
        if not report:
            return None
        if not isinstance(report, dict) or not report.get('file'):
            return report

        download_url = reverse('product-import-error-report', kwargs={'pk': obj.pk})
        request = self.context.get('request')
        if request:
            download_url = request.build_absolute_uri(download_url)
        return {
            'available': True,
            'format': report.get('format', 'csv'),
            'download_url': download_url,
        }


class ImportJobListSerializer(ImportJobBaseSerializer):
    pass


class ImportJobDetailSerializer(ImportJobBaseSerializer):
    pass


class ImportJobErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJobError
        fields = (
            'row_number', 'row_data', 'error_message',
            'field_errors', 'created_at',
        )


class ReviewImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewImage
        fields = ('id', 'image')


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    images = ReviewImageSerializer(many=True, read_only=True)
    product = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            'id', 'product', 'order', 'user_name', 'rating', 'text',
            'status', 'images', 'is_verified_purchase', 'created_at', 'updated_at',
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_user_name(self, obj):
        return obj.user.full_name or 'Покупатель'

    @extend_schema_field(serializers.DictField())
    def get_product(self, obj):
        return {'id': obj.product_id, 'slug': obj.product.slug, 'name': obj.product.name}

    @extend_schema_field(serializers.DictField())
    def get_order(self, obj):
        return {'id': obj.order_id, 'order_number': obj.order.order_number}


class ReviewListSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'user_name', 'rating', 'text', 'created_at')

    @extend_schema_field(OpenApiTypes.STR)
    def get_user_name(self, obj):
        return obj.user.full_name or 'Покупатель'


class ReviewCreateSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(required=False, write_only=True, min_value=1)
    product_slug = serializers.SlugField(required=False, write_only=True)
    order_id = serializers.IntegerField(required=False, write_only=True, min_value=1)
    order_number = serializers.CharField(required=False, write_only=True)

    class Meta:
        model = Review
        fields = (
            'id', 'product', 'order',
            'product_id', 'product_slug', 'order_id', 'order_number',
            'rating', 'text', 'status', 'created_at',
        )
        read_only_fields = ('id', 'product', 'order', 'status', 'created_at')

    def validate(self, attrs):
        request = self.context['request']
        product = self._resolve_product(attrs)
        order = self._resolve_order(attrs)
        try:
            ProductReviewService.can_review_product(request.user, product, order)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(self._error_detail(exc)) from exc
        attrs['product'] = product
        attrs['order'] = order
        return attrs

    def create(self, validated_data):
        product = validated_data.pop('product')
        order = validated_data.pop('order')
        validated_data.pop('product_id', None)
        validated_data.pop('product_slug', None)
        validated_data.pop('order_id', None)
        validated_data.pop('order_number', None)
        try:
            return ProductReviewService.create_review(
                user=self.context['request'].user,
                product=product,
                order=order,
                **validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(self._error_detail(exc)) from exc

    @staticmethod
    def _resolve_product(attrs):
        product_id = attrs.get('product_id')
        product_slug = attrs.get('product_slug')
        if not product_id and not product_slug:
            raise serializers.ValidationError(
                {'product': 'Передайте product_id или product_slug.'}
            )
        lookup = {'pk': product_id} if product_id else {'slug': product_slug}
        try:
            return Product.objects.get(**lookup)
        except Product.DoesNotExist as exc:
            raise serializers.ValidationError({'product': 'Товар не найден.'}) from exc

    @staticmethod
    def _resolve_order(attrs):
        order_id = attrs.get('order_id')
        order_number = attrs.get('order_number')
        if not order_id and not order_number:
            raise serializers.ValidationError(
                {'order': 'Передайте order_id или order_number.'}
            )
        lookup = {'pk': order_id} if order_id else {'order_number': order_number}
        try:
            return Order.objects.get(**lookup)
        except Order.DoesNotExist as exc:
            raise serializers.ValidationError({'order': 'Заказ не найден.'}) from exc

    @staticmethod
    def _error_detail(exc):
        if hasattr(exc, 'messages') and exc.messages:
            return exc.messages[0]
        return str(exc)


# Лёгкий сериализатор для списков
class ProductListSerializer(serializers.ModelSerializer):
    main_image = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    discount_percent = serializers.ReadOnlyField()
    discount = serializers.ReadOnlyField()
    is_sale = serializers.ReadOnlyField()
    min_price = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    available_colors = serializers.SerializerMethodField()
    available_sizes = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'sku', 'category', 'brand',
            'brand_name', 'category_name',
            'price', 'old_price', 'discount', 'discount_percent',
            'is_new', 'is_sale', 'is_active',
            'main_image', 'min_price', 'in_stock',
            'available_colors', 'available_sizes',
            'rating', 'average_rating', 'reviews_count',
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_main_image(self, obj):
        images = list(obj.images.all())
        img = next((image for image in images if image.is_main), None)
        if img is None and images:
            img = images[0]
        if img:
            request = self.context.get('request')
            return request.build_absolute_uri(img.image.url) if request else img.image.url
        return None

    @extend_schema_field(serializers.DictField())
    def get_category(self, obj):
        if not obj.category:
            return None
        return {'id': obj.category.id, 'name': obj.category.name, 'slug': obj.category.slug}

    @extend_schema_field(serializers.DictField())
    def get_brand(self, obj):
        if not obj.brand:
            return None
        return {'id': obj.brand.id, 'name': obj.brand.name, 'slug': obj.brand.slug}

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_min_price(self, obj):
        annotated_min_price = getattr(obj, '_min_price', None)
        if annotated_min_price is not None:
            return annotated_min_price

        variants = [variant for variant in obj.variants.all() if variant.is_active]
        if not variants:
            return obj.price
        return min(
            variant.variant_price if variant.variant_price is not None else obj.price
            for variant in variants
        )

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_in_stock(self, obj):
        annotated_in_stock = getattr(obj, '_in_stock', None)
        if annotated_in_stock is not None:
            return annotated_in_stock
        return any(variant.in_stock for variant in obj.variants.all())

    @extend_schema_field(ColorSerializer(many=True))
    def get_available_colors(self, obj):
        colors = {}
        for variant in obj.variants.all():
            if variant.in_stock and variant.color:
                colors[variant.color.id] = variant.color
        return ColorSerializer(colors.values(), many=True).data

    @extend_schema_field(SizeSerializer(many=True))
    def get_available_sizes(self, obj):
        sizes = {}
        for variant in obj.variants.all():
            if variant.in_stock and variant.size:
                sizes[variant.size.id] = variant.size
        return SizeSerializer(sizes.values(), many=True).data

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_average_rating(self, obj):
        average_rating = getattr(obj, '_average_rating', None)
        if average_rating is None:
            return None
        return round(float(average_rating), 2)

    @extend_schema_field(OpenApiTypes.INT)
    def get_reviews_count(self, obj):
        reviews_count = getattr(obj, '_published_reviews_count', None)
        if reviews_count is not None:
            return reviews_count
        return obj.reviews.filter(status=Review.Status.PUBLISHED).count()


# Детальный сериализатор для карточки товара
class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    media = serializers.SerializerMethodField()
    videos = serializers.SerializerMethodField()
    variants = ProductVariantSerializer(many=True, read_only=True)
    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    reviews = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    discount_percent = serializers.ReadOnlyField()
    discount = serializers.ReadOnlyField()
    is_sale = serializers.ReadOnlyField()
    average_rating = serializers.SerializerMethodField()
    available_sizes = serializers.SerializerMethodField()
    available_colors = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'sku',
            'category', 'brand',
            'description', 'composition', 'material', 'season',
            'price', 'old_price', 'discount', 'discount_percent', 'is_sale',
            'images', 'media', 'videos', 'variants',
            'available_sizes', 'available_colors',
            'rating', 'average_rating', 'reviews_count', 'reviews',
            'is_new', 'is_featured', 'is_active',
            'seo_title', 'seo_description', 'meta_title', 'meta_description',
            'created_at',
        )

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_videos(self, obj):
        return [
            {'video': v.video.url if v.video else None, 'youtube_url': v.youtube_url}
            for v in obj.videos.all()
        ]

    @extend_schema_field(ProductMediaSerializer(many=True))
    def get_media(self, obj):
        media = getattr(obj, 'active_media', None)
        if media is None:
            media = obj.media.filter(is_active=True)
        return ProductMediaSerializer(
            media,
            many=True,
            context=self.context,
        ).data

    @extend_schema_field(ReviewListSerializer(many=True))
    def get_reviews(self, obj):
        reviews = getattr(obj, 'approved_reviews', None)
        if reviews is None:
            reviews = (
                obj.reviews
                .filter(status=Review.Status.PUBLISHED)
                .select_related('user')
            )
        return ReviewListSerializer(list(reviews)[:5], many=True).data

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_average_rating(self, obj):
        average_rating = getattr(obj, '_average_rating', None)
        if average_rating is not None:
            return round(float(average_rating), 2)
        reviews = getattr(obj, 'approved_reviews', None)
        if reviews is not None:
            ratings = [review.rating for review in reviews]
            if not ratings:
                return None
            return round(sum(ratings) / len(ratings), 2)
        average_rating = obj.reviews.filter(
            status=Review.Status.PUBLISHED,
        ).aggregate(models.Avg('rating'))['rating__avg']
        return round(float(average_rating), 2) if average_rating is not None else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_reviews_count(self, obj):
        reviews_count = getattr(obj, '_published_reviews_count', None)
        if reviews_count is not None:
            return reviews_count
        reviews = getattr(obj, 'approved_reviews', None)
        if reviews is not None:
            return len(reviews)
        return obj.reviews.filter(status=Review.Status.PUBLISHED).count()

    @extend_schema_field(SizeSerializer(many=True))
    def get_available_sizes(self, obj):
        sizes = {}
        for variant in obj.variants.all():
            if variant.is_active and variant.size:
                sizes[variant.size.id] = variant.size
        ordered_sizes = sorted(sizes.values(), key=lambda size: (size.size_type, size.sort_order, size.value))
        return SizeSerializer(ordered_sizes, many=True).data

    @extend_schema_field(ColorSerializer(many=True))
    def get_available_colors(self, obj):
        colors = {}
        for variant in obj.variants.all():
            if variant.is_active and variant.color:
                colors[variant.color.id] = variant.color
        ordered_colors = sorted(colors.values(), key=lambda color: color.name)
        return ColorSerializer(ordered_colors, many=True).data


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = (
            'id', 'title', 'subtitle', 'button_text',
            'image', 'image_mobile', 'link', 'position', 'sort_order',
        )


class PromoCheckSerializer(serializers.Serializer):
    code = serializers.CharField()
    order_amount = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate(self, data):
        try:
            promo = Promo.objects.get(code=data['code'].upper())
        except Promo.DoesNotExist:
            raise serializers.ValidationError({'code': 'Промокод не найден'})
        if not promo.is_valid(data['order_amount']):
            raise serializers.ValidationError({'code': 'Промокод недействителен или истёк'})
        data['promo'] = promo
        return data

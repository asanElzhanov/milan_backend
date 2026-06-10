from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from .models import (
    Banner, Brand, Category, Color, Product, ProductImage,
    ProductMedia, ProductVariant, Promo, Review, ReviewImage, Size,
)


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
    stock = serializers.IntegerField(source='stock_quantity', read_only=True)
    sku_variant = serializers.CharField(source='sku', read_only=True)
    extra_price = serializers.SerializerMethodField()
    in_stock = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()
    final_price = serializers.ReadOnlyField()

    class Meta:
        model = ProductVariant
        fields = (
            'id', 'color', 'size',
            'sku', 'stock_quantity', 'variant_price', 'is_active',
            'stock', 'sku_variant', 'extra_price',
            'in_stock', 'is_available', 'final_price',
        )

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_extra_price(self, obj):
        if obj.variant_price is None:
            return '0.00'
        return str(obj.variant_price - obj.product.price)


class ReviewImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewImage
        fields = ('id', 'image')


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    images = ReviewImageSerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = ('id', 'user_name', 'rating', 'text', 'images', 'is_verified_purchase', 'created_at')

    @extend_schema_field(OpenApiTypes.STR)
    def get_user_name(self, obj):
        return obj.user.full_name or 'Покупатель'


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ('rating', 'text')

    def create(self, validated_data):
        return Review.objects.create(
            user=self.context['request'].user,
            product=self.context['product'],
            **validated_data,
        )


# Лёгкий сериализатор для списков
class ProductListSerializer(serializers.ModelSerializer):
    main_image = serializers.SerializerMethodField()
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    discount_percent = serializers.ReadOnlyField()
    discount = serializers.ReadOnlyField()
    is_sale = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = (
            'id', 'name', 'slug', 'sku', 'brand_name', 'category_name',
            'price', 'old_price', 'discount', 'discount_percent',
            'is_sale', 'main_image', 'rating', 'reviews_count', 'is_new',
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_main_image(self, obj):
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        if img:
            request = self.context.get('request')
            return request.build_absolute_uri(img.image.url) if request else img.image.url
        return None


# Детальный сериализатор для карточки товара
class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    media = serializers.SerializerMethodField()
    videos = serializers.SerializerMethodField()
    variants = ProductVariantSerializer(many=True, read_only=True)
    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    reviews = serializers.SerializerMethodField()
    discount_percent = serializers.ReadOnlyField()
    discount = serializers.ReadOnlyField()
    is_sale = serializers.ReadOnlyField()
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
            'rating', 'reviews_count', 'reviews',
            'is_new', 'is_featured',
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
        return ProductMediaSerializer(
            obj.media.filter(is_active=True),
            many=True,
            context=self.context,
        ).data

    @extend_schema_field(ReviewSerializer(many=True))
    def get_reviews(self, obj):
        qs = obj.reviews.filter(is_approved=True)[:5]
        return ReviewSerializer(qs, many=True).data

    @extend_schema_field(SizeSerializer(many=True))
    def get_available_sizes(self, obj):
        sizes = Size.objects.filter(
            productvariant__product=obj,
            productvariant__stock_quantity__gt=0,
            productvariant__is_active=True,
        ).distinct()
        return SizeSerializer(sizes, many=True).data

    @extend_schema_field(ColorSerializer(many=True))
    def get_available_colors(self, obj):
        colors = Color.objects.filter(
            productvariant__product=obj,
            productvariant__stock_quantity__gt=0,
            productvariant__is_active=True,
        ).distinct()
        return ColorSerializer(colors, many=True).data


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ('id', 'title', 'subtitle', 'image', 'image_mobile', 'link', 'position')


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

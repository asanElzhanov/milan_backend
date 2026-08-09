from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from apps.common.statuses import get_status_labels
from .models import DeliveryMethod, Order, OrderItem, OrderStatusHistory, Cart, CartItem
from .services import CartService, CheckoutService


class DeliveryMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryMethod
        fields = (
            'id', 'name_ru', 'name_kz', 'name_en', 'code', 'slug', 'delivery_type',
            'description_ru', 'description_kz', 'description_en',
            'is_active', 'base_price', 'price_type',
            'free_from_amount', 'sort_order',
        )


class CartItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(source='variant.id', read_only=True)
    product_id = serializers.IntegerField(source='variant.product.id', read_only=True)
    product_name = serializers.CharField(source='variant.product.name_ru', read_only=True)
    product_name_ru = serializers.CharField(source='variant.product.name_ru', read_only=True)
    product_name_kz = serializers.CharField(source='variant.product.name_kz', read_only=True)
    product_name_en = serializers.CharField(source='variant.product.name_en', read_only=True)
    product_slug = serializers.CharField(source='variant.product.slug', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)
    color = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    available_stock = serializers.IntegerField(source='variant.stock_quantity', read_only=True)
    in_stock = serializers.BooleanField(source='variant.in_stock', read_only=True)

    class Meta:
        model = CartItem
        fields = (
            'id', 'variant_id', 'product_id', 'product_name',
            'product_name_ru', 'product_name_kz', 'product_name_en', 'product_slug',
            'sku', 'size', 'color', 'quantity', 'unit_price', 'line_total',
            'image', 'available_stock', 'in_stock',
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_color(self, obj):
        return obj.variant.color.name_ru if obj.variant.color else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_size(self, obj):
        return obj.variant.size.value if obj.variant.size else None

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_unit_price(self, obj):
        return str(CartService.get_effective_price(obj.variant))

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_line_total(self, obj):
        return str(CartService.get_effective_price(obj.variant) * obj.quantity)

    @extend_schema_field(OpenApiTypes.URI)
    def get_image(self, obj):
        images = list(obj.variant.product.images.all())
        image = next((item for item in images if item.is_main), None)
        if image is None and images:
            image = images[0]
        if not image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(image.image.url) if request else image.image.url


class CartSerializer(serializers.ModelSerializer):
    cart_token = serializers.SerializerMethodField()
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    promo_code = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    total_after_discount = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = (
            'cart_token', 'items', 'items_count', 'total_quantity',
            'subtotal', 'promo_code', 'discount_amount',
            'total_after_discount', 'total',
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_cart_token(self, obj):
        return str(obj.token) if obj.token else None

    def _totals(self, obj):
        if not hasattr(obj, '_cart_totals'):
            obj._cart_totals = CartService.recalculate_cart(obj)
        return obj._cart_totals

    @extend_schema_field(OpenApiTypes.INT)
    def get_items_count(self, obj):
        return self._totals(obj)['items_count']

    @extend_schema_field(OpenApiTypes.INT)
    def get_total_quantity(self, obj):
        return self._totals(obj)['total_quantity']

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_subtotal(self, obj):
        return str(self._totals(obj)['subtotal'])

    @extend_schema_field(OpenApiTypes.STR)
    def get_promo_code(self, obj):
        promo_code = self._totals(obj)['promo_code']
        return promo_code.code if promo_code else None

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_discount_amount(self, obj):
        return str(self._totals(obj)['discount_amount'])

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total_after_discount(self, obj):
        return str(self._totals(obj)['total_after_discount'])

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_total(self, obj):
        return str(self._totals(obj)['total'])


class CartItemAddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemQuantityUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartMergeSerializer(serializers.Serializer):
    guest_cart_token = serializers.UUIDField()


class CartPromoCodeApplySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    cart_token = serializers.UUIDField(required=False, write_only=True)


class OrderItemSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            'id', 'product_name', 'product_slug', 'sku',
            'size_name', 'color_name', 'unit_price',
            'quantity', 'total_price', 'image',
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_image(self, obj):
        images = list(obj.variant.product.images.all())
        image = next((item for item in images if item.is_main), None)
        if image is None and images:
            image = images[0]
        if not image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(image.image.url) if request else image.image.url


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    old_status_labels = serializers.SerializerMethodField()
    new_status_labels = serializers.SerializerMethodField()

    class Meta:
        model = OrderStatusHistory
        fields = (
            'old_status', 'old_status_labels', 'new_status', 'new_status_labels',
            'changed_by', 'comment', 'created_at',
        )

    @extend_schema_field(serializers.DictField(child=serializers.CharField(), allow_null=True))
    def get_old_status_labels(self, obj):
        return get_status_labels('order', obj.old_status) if obj.old_status else None

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_new_status_labels(self, obj):
        return get_status_labels('order', obj.new_status)


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True)
    status_labels = serializers.SerializerMethodField()
    payment_status_labels = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'order_number', 'status', 'status_labels',
            'payment_status', 'payment_status_labels',
            'delivery_method', 'delivery_method_code', 'delivery_method_name',
            'items_total', 'delivery_price', 'delivery_requires_manager_calculation',
            'delivery_price_is_final', 'promo_code_text', 'discount_amount',
            'total_amount', 'items_count', 'created_at',
        )

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_status_labels(self, obj):
        return get_status_labels('order', obj.status)

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_payment_status_labels(self, obj):
        return get_status_labels('order_payment', obj.payment_status)


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    status_labels = serializers.SerializerMethodField()
    payment_status_labels = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'order_number', 'customer_name', 'phone', 'email',
            'city', 'delivery_address', 'delivery_method',
            'delivery_method_code', 'delivery_method_name',
            'items_total', 'delivery_price', 'delivery_requires_manager_calculation',
            'delivery_price_is_final', 'promo_code_text', 'discount_amount',
            'total_amount', 'status', 'status_labels',
            'payment_status', 'payment_status_labels', 'comment',
            'items', 'status_history',
            'created_at',
        )

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_status_labels(self, obj):
        return get_status_labels('order', obj.status)

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_payment_status_labels(self, obj):
        return get_status_labels('order_payment', obj.payment_status)


OrderSerializer = OrderDetailSerializer


class CheckoutSerializer(serializers.Serializer):
    """Создание заказа из корзины"""
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    comment = serializers.CharField(required=False, allow_blank=True)

    delivery_method = serializers.CharField(max_length=50, required=False, allow_blank=True)
    delivery_method_code = serializers.CharField(max_length=50, required=False, allow_blank=True, write_only=True)
    delivery_method_id = serializers.IntegerField(min_value=1, required=False, write_only=True)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    delivery_city = serializers.CharField(required=False, allow_blank=True, write_only=True)
    delivery_country = serializers.CharField(default='Казахстан', write_only=True)
    delivery_postal_code = serializers.CharField(required=False, allow_blank=True)
    cart_token = serializers.UUIDField(required=False, write_only=True)
    promo_code = serializers.CharField(max_length=50, required=False, allow_blank=True, write_only=True)
    discount_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        write_only=True,
    )
    delivery_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        write_only=True,
    )

    def validate(self, data):
        cart = self.context['cart']
        if not cart.items.exists():
            raise serializers.ValidationError('Корзина пуста')

        customer_name = data.get('customer_name', '').strip()
        if not customer_name:
            customer_name = f"{data.get('first_name', '').strip()} {data.get('last_name', '').strip()}".strip()
        if not customer_name:
            raise serializers.ValidationError({'customer_name': 'Укажите имя покупателя'})
        data['customer_name'] = customer_name

        if not data.get('city') and data.get('delivery_city'):
            data['city'] = data['delivery_city']

        delivery_method = data.get('delivery_method') or data.get('delivery_method_code')
        if data.get('delivery_method_id'):
            delivery_method = data['delivery_method_id']
        if not delivery_method:
            raise serializers.ValidationError({'delivery_method': 'Укажите способ доставки'})
        data['delivery_method'] = delivery_method

        return data

    def create(self, validated_data):
        return CheckoutService.checkout(
            cart=self.context['cart'],
            user=self.context.get('user'),
            customer_name=validated_data['customer_name'],
            phone=validated_data['phone'],
            email=validated_data['email'],
            city=validated_data.get('city', ''),
            delivery_address=validated_data.get('delivery_address', ''),
            delivery_method=validated_data['delivery_method'],
            promo_code=validated_data.get('promo_code') or None,
            comment=validated_data.get('comment', ''),
            anonymous_id_hash=self.context.get('anonymous_id_hash', ''),
        )


OrderCreateSerializer = CheckoutSerializer

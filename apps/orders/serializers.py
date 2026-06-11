from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory, Cart, CartItem
from .services import CartService, CheckoutService


class CartItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(source='variant.id', read_only=True)
    product_id = serializers.IntegerField(source='variant.product.id', read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
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
            'id', 'variant_id', 'product_id', 'product_name', 'product_slug',
            'sku', 'size', 'color', 'quantity', 'unit_price', 'line_total',
            'image', 'available_stock', 'in_stock',
        )

    @extend_schema_field(OpenApiTypes.STR)
    def get_color(self, obj):
        return obj.variant.color.name if obj.variant.color else None

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
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = (
            'cart_token', 'items', 'items_count', 'total_quantity',
            'subtotal', 'total',
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


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            'id', 'product_name', 'product_slug', 'sku',
            'size_name', 'color_name', 'unit_price',
            'quantity', 'total_price',
        )


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ('old_status', 'new_status', 'changed_by', 'comment', 'created_at')


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = (
            'order_number', 'status', 'payment_status',
            'total_amount', 'items_count', 'created_at',
        )


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            'order_number', 'customer_name', 'phone', 'email',
            'city', 'delivery_address', 'delivery_method',
            'total_amount', 'status', 'payment_status', 'comment',
            'items', 'status_history',
            'created_at',
        )


OrderSerializer = OrderDetailSerializer


class CheckoutSerializer(serializers.Serializer):
    """Создание заказа из корзины"""
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    comment = serializers.CharField(required=False, allow_blank=True)

    delivery_method = serializers.ChoiceField(choices=Order.DeliveryMethod.choices)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    delivery_city = serializers.CharField(required=False, allow_blank=True, write_only=True)
    delivery_country = serializers.CharField(default='Казахстан', write_only=True)
    delivery_postal_code = serializers.CharField(required=False, allow_blank=True)
    cart_token = serializers.UUIDField(required=False, write_only=True)

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
            comment=validated_data.get('comment', ''),
        )


OrderCreateSerializer = CheckoutSerializer

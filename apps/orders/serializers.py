from django.db import models, transaction
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory, Cart, CartItem
from apps.catalog.models import Promo
from apps.catalog.services import StockService
from .services import CartService


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
        fields = ('status', 'comment', 'created_at')


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_number', 'user', 'customer_name', 'phone', 'email',
            'city', 'delivery_address', 'delivery_method',
            'total_amount', 'status', 'payment_status', 'comment',
            'items', 'status_history',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'order_number', 'user', 'total_amount', 'status',
            'payment_status', 'created_at', 'updated_at',
        )


class OrderCreateSerializer(serializers.Serializer):
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

    promo_code = serializers.CharField(required=False, allow_blank=True)

    DELIVERY_COSTS = {
        Order.DeliveryMethod.COURIER: 1500,
        Order.DeliveryMethod.PICKUP: 0,
        Order.DeliveryMethod.POST: 800,
        Order.DeliveryMethod.OTHER: 0,
    }

    def validate(self, data):
        cart = self.context['cart']
        if not cart.items.exists():
            raise serializers.ValidationError('Корзина пуста')

        # Проверяем промокод
        if data.get('promo_code'):
            try:
                promo = Promo.objects.get(code=data['promo_code'].upper(), is_active=True)
                if not promo.is_valid():
                    raise serializers.ValidationError({'promo_code': 'Промокод недействителен'})
                data['promo'] = promo
            except Promo.DoesNotExist:
                raise serializers.ValidationError({'promo_code': 'Промокод не найден'})

        customer_name = data.get('customer_name', '').strip()
        if not customer_name:
            customer_name = f"{data.get('first_name', '').strip()} {data.get('last_name', '').strip()}".strip()
        if not customer_name:
            raise serializers.ValidationError({'customer_name': 'Укажите имя покупателя'})
        data['customer_name'] = customer_name

        if not data.get('city') and data.get('delivery_city'):
            data['city'] = data['delivery_city']

        return data

    @transaction.atomic
    def create(self, validated_data):
        cart = self.context['cart']
        promo = validated_data.pop('promo', None)

        # Считаем subtotal
        items_data = list(cart.items.select_related(
            'variant__product', 'variant__color', 'variant__size'
        ))
        subtotal = sum(item.total_price for item in items_data)
        delivery_cost = self.DELIVERY_COSTS.get(validated_data['delivery_method'], 0)

        discount_amount = promo.calculate_discount(subtotal) if promo else 0
        total = subtotal - discount_amount + delivery_cost

        order = Order.objects.create(
            user=self.context.get('user'),
            customer_name=validated_data['customer_name'],
            phone=validated_data['phone'],
            email=validated_data['email'],
            city=validated_data.get('city', ''),
            delivery_address=validated_data.get('delivery_address', ''),
            delivery_method=validated_data['delivery_method'],
            total_amount=total,
            status=Order.Status.NEW,
            payment_status=Order.PaymentStatus.UNPAID,
            comment=validated_data.get('comment', ''),
        )

        # Создаём позиции + уменьшаем остаток
        for item in items_data:
            variant = item.variant
            OrderItem.objects.create(
                order=order,
                variant=variant,
                product_name=variant.product.name,
                product_slug=variant.product.slug,
                sku=variant.sku,
                size_name=variant.size.value if variant.size else '',
                color_name=variant.color.name if variant.color else '',
                quantity=item.quantity,
                unit_price=variant.final_price,
            )
            StockService.sale(
                variant=variant,
                quantity=item.quantity,
                user=self.context.get('user'),
                comment=f'Заказ #{order.order_number}',
            )

        # Используем промокод
        if promo:
            Promo.objects.filter(pk=promo.pk).update(used_count=models.F('used_count') + 1)

        # Очищаем корзину
        cart.items.all().delete()

        # Запись в историю
        OrderStatusHistory.objects.create(order=order, status=Order.Status.NEW)

        return order

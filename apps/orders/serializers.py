from django.db import transaction
from django.db import models
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from .models import Order, OrderItem, OrderStatusHistory, Cart, CartItem
from apps.catalog.models import ProductVariant, Promo
from apps.catalog.serializers import ProductListSerializer


class CartItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(write_only=True)
    product = serializers.SerializerMethodField()
    color = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    total_price = serializers.ReadOnlyField()

    class Meta:
        model = CartItem
        fields = ('id', 'variant_id', 'product', 'color', 'size', 'quantity', 'unit_price', 'total_price')

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_product(self, obj):
        return {
            'id': obj.variant.product.id,
            'name': obj.variant.product.name,
            'slug': obj.variant.product.slug,
        }

    @extend_schema_field(OpenApiTypes.STR)
    def get_color(self, obj):
        return obj.variant.color.name if obj.variant.color else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_size(self, obj):
        return obj.variant.size.value if obj.variant.size else None

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_unit_price(self, obj):
        return str(obj.variant.final_price)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(source='cart_items', many=True, read_only=True)
    total = serializers.ReadOnlyField()
    items_count = serializers.ReadOnlyField()

    class Meta:
        model = Cart
        fields = ('id', 'items', 'total', 'items_count', 'updated_at')


class CartItemAddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_variant_id(self, value):
        try:
            variant = ProductVariant.objects.get(pk=value)
        except ProductVariant.DoesNotExist:
            raise serializers.ValidationError('Вариант товара не найден')
        if not variant.is_available:
            raise serializers.ValidationError('Товар недоступен')
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            'id', 'product_name', 'product_sku', 'color_name',
            'size_value', 'quantity', 'unit_price', 'total_price'
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
            'id', 'number', 'status',
            'first_name', 'last_name', 'email', 'phone',
            'delivery_method', 'delivery_address', 'delivery_city',
            'delivery_country', 'tracking_number',
            'subtotal', 'discount_amount', 'delivery_cost', 'total',
            'promo_code', 'comment',
            'items', 'status_history',
            'created_at',
        )
        read_only_fields = ('number', 'status', 'subtotal', 'discount_amount', 'total')


class OrderCreateSerializer(serializers.Serializer):
    """Создание заказа из корзины"""
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    comment = serializers.CharField(required=False, allow_blank=True)

    delivery_method = serializers.ChoiceField(choices=Order.DeliveryMethod.choices)
    delivery_address = serializers.CharField(required=False, allow_blank=True)
    delivery_city = serializers.CharField(required=False, allow_blank=True)
    delivery_country = serializers.CharField(default='Казахстан')
    delivery_postal_code = serializers.CharField(required=False, allow_blank=True)

    promo_code = serializers.CharField(required=False, allow_blank=True)

    DELIVERY_COSTS = {
        Order.DeliveryMethod.COURIER: 1500,
        Order.DeliveryMethod.PICKUP: 0,
        Order.DeliveryMethod.KAZPOST: 800,
        Order.DeliveryMethod.DHL: 5000,
    }

    def validate(self, data):
        cart = self.context['cart']
        if not cart.cart_items.exists():
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

        return data

    @transaction.atomic
    def create(self, validated_data):
        cart = self.context['cart']
        promo = validated_data.pop('promo', None)

        # Считаем subtotal
        items_data = list(cart.cart_items.select_related(
            'variant__product', 'variant__color', 'variant__size'
        ))
        subtotal = sum(item.total_price for item in items_data)
        delivery_cost = self.DELIVERY_COSTS.get(validated_data['delivery_method'], 0)

        discount_amount = promo.calculate_discount(subtotal) if promo else 0
        total = subtotal - discount_amount + delivery_cost

        order = Order.objects.create(
            user=self.context.get('user'),
            subtotal=subtotal,
            discount_amount=discount_amount,
            delivery_cost=delivery_cost,
            total=total,
            promo_code=promo.code if promo else '',
            **{k: v for k, v in validated_data.items() if k != 'promo_code' or True},
        )

        # Создаём позиции + уменьшаем остаток
        for item in items_data:
            variant = item.variant
            OrderItem.objects.create(
                order=order,
                product=variant.product,
                variant=variant,
                product_name=variant.product.name,
                product_sku=variant.product.sku,
                color_name=variant.color.name if variant.color else '',
                size_value=variant.size.value if variant.size else '',
                quantity=item.quantity,
                unit_price=variant.final_price,
            )
            # Уменьшаем склад
            ProductVariant.objects.filter(pk=variant.pk).update(
                stock_quantity=models.F('stock_quantity') - item.quantity
            )

        # Используем промокод
        if promo:
            Promo.objects.filter(pk=promo.pk).update(used_count=models.F('used_count') + 1)

        # Очищаем корзину
        cart.cart_items.all().delete()

        # Запись в историю
        OrderStatusHistory.objects.create(order=order, status=Order.Status.PENDING)

        return order

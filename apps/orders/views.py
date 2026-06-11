from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
import uuid

from .models import Order, Cart, CartItem
from .serializers import (
    CartSerializer, CartItemAddSerializer,
    OrderSerializer, OrderCreateSerializer,
)
from apps.notifications.tasks import send_order_confirmation_email


OrderDetailResponseSerializer = inline_serializer(
    name='OrderDetailResponse',
    fields={'detail': serializers.CharField()},
)
CartItemQuantityUpdateSerializer = inline_serializer(
    name='CartItemQuantityUpdate',
    fields={'quantity': serializers.IntegerField(min_value=1)},
)


def get_or_create_cart(request):
    """Получить корзину — для авторизованного по user, для гостя по token."""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)
    else:
        raw_token = request.headers.get('X-Cart-Token') or request.query_params.get('cart_token')
        token = None
        if raw_token:
            try:
                token = uuid.UUID(str(raw_token))
            except ValueError:
                token = None

        if token:
            cart, _ = Cart.objects.get_or_create(token=token, user=None, defaults={'is_active': True})
        else:
            cart = Cart.objects.create(user=None, is_active=True)
    return cart


# ── Корзина ──────────────────────────────────────────────────────────────────

class CartView(APIView):
    """GET /orders/cart/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Получить текущую корзину',
        responses={200: CartSerializer},
    )
    def get(self, request):
        cart = get_or_create_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)


class CartAddView(APIView):
    """POST /orders/cart/add/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Добавить товар в корзину',
        request=CartItemAddSerializer,
        responses={200: CartSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def post(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = get_or_create_cart(request)

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant_id=serializer.validated_data['variant_id'],
            defaults={'quantity': serializer.validated_data['quantity']},
        )
        if not created:
            item.quantity += serializer.validated_data['quantity']
            item.save(update_fields=['quantity'])

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class CartItemUpdateView(APIView):
    """PATCH /orders/cart/items/<pk>/  — изменить количество"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Изменить количество товара в корзине',
        request=CartItemQuantityUpdateSerializer,
        responses={
            200: CartSerializer,
            400: OrderDetailResponseSerializer,
            404: OpenApiResponse(description='Позиция не найдена'),
        },
    )
    def patch(self, request, pk):
        cart = get_or_create_cart(request)
        item = get_object_or_404(CartItem, pk=pk, cart=cart)
        quantity = request.data.get('quantity', 1)
        if quantity < 1:
            return Response({'detail': 'Количество должно быть >= 1'}, status=400)
        item.quantity = quantity
        item.save(update_fields=['quantity'])
        return Response(CartSerializer(cart).data)


class CartItemDeleteView(APIView):
    """DELETE /orders/cart/items/<pk>/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Удалить позицию из корзины',
        responses={200: CartSerializer},
    )
    def delete(self, request, pk):
        cart = get_or_create_cart(request)
        CartItem.objects.filter(pk=pk, cart=cart).delete()
        return Response(CartSerializer(cart).data)


class CartClearView(APIView):
    """DELETE /orders/cart/clear/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Очистить корзину',
        responses={200: OrderDetailResponseSerializer},
    )
    def delete(self, request):
        cart = get_or_create_cart(request)
        cart.items.all().delete()
        return Response({'detail': 'Корзина очищена'})


# ── Заказы ────────────────────────────────────────────────────────────────────

class OrderCreateView(APIView):
    """POST /orders/ — оформить заказ"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Orders'],
        summary='Оформить заказ',
        request=OrderCreateSerializer,
        responses={201: OrderSerializer, 400: OpenApiResponse(description='Ошибка оформления заказа')},
    )
    def post(self, request):
        cart = get_or_create_cart(request)
        serializer = OrderCreateSerializer(
            data=request.data,
            context={
                'cart': cart,
                'user': request.user if request.user.is_authenticated else None,
            }
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        # Отправить email подтверждение через Celery
        send_order_confirmation_email.delay(order.id)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListView(generics.ListAPIView):
    """GET /orders/ — история заказов пользователя"""
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()
        return Order.objects.filter(user=self.request.user).prefetch_related('items')

    @extend_schema(
        tags=['Orders'],
        summary='История заказов пользователя',
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class OrderDetailView(generics.RetrieveAPIView):
    """GET /orders/<number>/"""
    serializer_class = OrderSerializer
    lookup_field = 'number'

    def get_permissions(self):
        return [permissions.AllowAny()]

    def get_queryset(self):
        return Order.objects.prefetch_related('items', 'status_history')

    @extend_schema(
        tags=['Orders'],
        summary='Детали заказа по номеру',
        responses={200: OrderSerializer, 404: OpenApiResponse(description='Заказ не найден')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import (
    CartSerializer, CartItemAddSerializer,
    OrderSerializer, OrderCreateSerializer,
)
from .services import CartError, CartService
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
        return CartService.get_or_create_user_cart(request.user)
    token = request.headers.get('X-Cart-Token') or request.query_params.get('cart_token')
    return CartService.get_or_create_guest_cart(token=token)


def cart_error_response(exc):
    detail = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
    return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)


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
        try:
            cart = get_or_create_cart(request)
        except CartError as exc:
            return cart_error_response(exc)
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
        try:
            cart = get_or_create_cart(request)
            _, cart = CartService.add_item(
                cart=cart,
                variant=serializer.validated_data['variant_id'],
                quantity=serializer.validated_data['quantity'],
            )
        except CartError as exc:
            return cart_error_response(exc)
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
        serializer = CartItemQuantityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = get_or_create_cart(request)
            _, cart = CartService.update_item(
                cart=cart,
                item_or_variant=pk,
                quantity=serializer.validated_data['quantity'],
            )
        except CartError as exc:
            return cart_error_response(exc)
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
        try:
            cart = get_or_create_cart(request)
            cart = CartService.remove_item(cart=cart, item_or_variant=pk)
        except CartError as exc:
            return cart_error_response(exc)
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
        try:
            cart = get_or_create_cart(request)
            CartService.clear_cart(cart)
        except CartError as exc:
            return cart_error_response(exc)
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
        try:
            cart = get_or_create_cart(request)
        except CartError as exc:
            return cart_error_response(exc)
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

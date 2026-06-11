from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ProductImage

from .models import Order
from .serializers import (
    CartItemAddSerializer,
    CartItemQuantityUpdateSerializer,
    CartMergeSerializer,
    CartSerializer,
    OrderCreateSerializer,
    OrderSerializer,
)
from .services import CartError, CartNotFoundError, CartService
from apps.notifications.tasks import send_order_confirmation_email


OrderDetailResponseSerializer = inline_serializer(
    name='OrderDetailResponse',
    fields={'detail': serializers.CharField()},
)
CartTokenHeader = OpenApiParameter(
    name='X-Cart-Token',
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description='Guest cart token returned as cart_token.',
)


def get_cart_token(request):
    return request.headers.get('X-Cart-Token')


def get_current_cart(request, *, allow_create=False):
    """Получить корзину — для авторизованного по user, для гостя по token."""
    if request.user.is_authenticated:
        cart = CartService.get_or_create_user_cart(request.user)
    else:
        token = get_cart_token(request)
        if not token and not allow_create:
            raise CartNotFoundError('Передайте X-Cart-Token.')
        cart = CartService.get_or_create_guest_cart(token=token)
    return load_cart_for_response(cart)


def load_cart_for_response(cart):
    return (
        cart.__class__.objects
        .prefetch_related(
            Prefetch(
                'items',
                queryset=cart.items.model.objects.select_related(
                    'variant__product',
                    'variant__size',
                    'variant__color',
                ).prefetch_related(
                    Prefetch(
                        'variant__product__images',
                        queryset=ProductImage.objects.order_by('sort_order', 'id'),
                    )
                ).order_by('id'),
            )
        )
        .get(pk=cart.pk)
    )


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
        parameters=[CartTokenHeader],
        responses={200: CartSerializer},
    )
    def get(self, request):
        try:
            cart = get_current_cart(request)
        except CartError as exc:
            return cart_error_response(exc)
        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)


class CartAddView(APIView):
    """POST /orders/cart/items/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Добавить товар в корзину',
        parameters=[CartTokenHeader],
        request=CartItemAddSerializer,
        responses={200: CartSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def post(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = get_current_cart(request, allow_create=True)
            _, cart = CartService.add_item(
                cart=cart,
                variant=serializer.validated_data['variant_id'],
                quantity=serializer.validated_data['quantity'],
            )
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        return Response(CartSerializer(cart, context={'request': request}).data, status=status.HTTP_200_OK)


class CartItemUpdateView(APIView):
    """PATCH/DELETE /orders/cart/items/<pk>/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Изменить количество товара в корзине',
        parameters=[CartTokenHeader],
        request=CartItemQuantityUpdateSerializer,
        responses={
            200: CartSerializer,
            400: OrderDetailResponseSerializer,
        },
    )
    def patch(self, request, pk):
        serializer = CartItemQuantityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = get_current_cart(request)
            _, cart = CartService.update_item_by_id(
                cart=cart,
                item_id=pk,
                quantity=serializer.validated_data['quantity'],
            )
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        return Response(CartSerializer(cart, context={'request': request}).data)

    @extend_schema(
        tags=['Cart'],
        summary='Удалить позицию из корзины',
        parameters=[CartTokenHeader],
        responses={200: CartSerializer},
    )
    def delete(self, request, pk):
        try:
            cart = get_current_cart(request)
            cart = CartService.remove_item_by_id(cart=cart, item_id=pk)
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        return Response(CartSerializer(cart, context={'request': request}).data)


class CartItemDeleteView(APIView):
    """DELETE /orders/cart/items/<pk>/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Удалить позицию из корзины',
        parameters=[CartTokenHeader],
        responses={200: CartSerializer},
    )
    def delete(self, request, pk):
        try:
            cart = get_current_cart(request)
            cart = CartService.remove_item_by_id(cart=cart, item_id=pk)
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        return Response(CartSerializer(cart, context={'request': request}).data)


class CartClearView(APIView):
    """DELETE /orders/cart/clear/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Очистить корзину',
        parameters=[CartTokenHeader],
        responses={200: CartSerializer},
    )
    def delete(self, request):
        try:
            cart = get_current_cart(request)
            cart = CartService.clear_cart(cart)
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        return Response(CartSerializer(cart, context={'request': request}).data)


class CartMergeView(APIView):
    """POST /orders/cart/merge/"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Cart'],
        summary='Объединить гостевую корзину с корзиной пользователя',
        request=CartMergeSerializer,
        responses={200: CartSerializer, 400: OrderDetailResponseSerializer},
    )
    def post(self, request):
        serializer = CartMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = CartService.merge_guest_cart_to_user_cart(
                guest_token=serializer.validated_data['guest_cart_token'],
                user=request.user,
            )
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        return Response(CartSerializer(cart, context={'request': request}).data)


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
            cart = get_current_cart(request)
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
    """GET /orders/<order_number>/"""
    serializer_class = OrderSerializer
    lookup_field = 'order_number'

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

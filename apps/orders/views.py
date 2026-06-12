from django.db.models import Count, Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema, inline_serializer
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ProductImage

from .models import DeliveryMethod, Order
from .serializers import (
    CartItemAddSerializer,
    CartItemQuantityUpdateSerializer,
    CartMergeSerializer,
    CartPromoCodeApplySerializer,
    CartSerializer,
    CheckoutSerializer,
    DeliveryMethodSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderCreateSerializer,
    OrderSerializer,
)
from .services import CartError, CartNotFoundError, CartService, CheckoutError, PromoCodeError
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
    token = request.headers.get('X-Cart-Token')
    if token:
        return token
    data = getattr(request, 'data', None)
    if isinstance(data, dict):
        return data.get('cart_token')
    return None


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
        .select_related('promo_code')
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


def load_order_for_response(order):
    return (
        Order.objects
        .select_related('delivery_method_ref')
        .prefetch_related('items', 'status_history')
        .get(pk=order.pk)
    )


def checkout_response(request):
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
    try:
        order = serializer.save()
    except (CartError, CheckoutError) as exc:
        return cart_error_response(exc)
    order = load_order_for_response(order)

    # Отправить email подтверждение через Celery
    send_order_confirmation_email.delay(order.id)

    return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


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


class CartPromoCodeApplyView(APIView):
    """POST /orders/cart/promo-code/apply/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Применить промокод к корзине',
        parameters=[CartTokenHeader],
        request=CartPromoCodeApplySerializer,
        responses={200: CartSerializer, 400: OpenApiResponse(description='Промокод не применён')},
    )
    def post(self, request):
        serializer = CartPromoCodeApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cart = get_current_cart(request)
            cart = CartService.apply_promo_code(
                cart=cart,
                code=serializer.validated_data['code'],
                user=request.user if request.user.is_authenticated else None,
            )
            cart = load_cart_for_response(cart)
        except (CartError, PromoCodeError) as exc:
            return cart_error_response(exc)
        data = CartSerializer(cart, context={'request': request}).data
        data['message'] = 'Промокод применён.'
        return Response(data, status=status.HTTP_200_OK)


class CartPromoCodeView(APIView):
    """DELETE /orders/cart/promo-code/"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Cart'],
        summary='Удалить промокод из корзины',
        parameters=[CartTokenHeader],
        responses={200: CartSerializer, 400: OrderDetailResponseSerializer},
    )
    def delete(self, request):
        try:
            cart = get_current_cart(request)
            cart = CartService.remove_promo_code(cart)
            cart = load_cart_for_response(cart)
        except CartError as exc:
            return cart_error_response(exc)
        data = CartSerializer(cart, context={'request': request}).data
        data['message'] = 'Промокод удалён.'
        return Response(data)


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

class DeliveryMethodListView(generics.ListAPIView):
    """GET /orders/delivery-methods/"""
    serializer_class = DeliveryMethodSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return DeliveryMethod.objects.filter(is_active=True).order_by('sort_order', 'name')

    @extend_schema(
        tags=['Orders / Delivery Methods'],
        summary='Список способов доставки',
        responses={200: DeliveryMethodSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CheckoutView(APIView):
    """POST /orders/checkout/ — оформить заказ"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Orders'],
        summary='Оформить заказ',
        parameters=[CartTokenHeader],
        request=CheckoutSerializer,
        responses={201: OrderSerializer, 400: OpenApiResponse(description='Ошибка оформления заказа')},
    )
    def post(self, request):
        return checkout_response(request)


class OrderListView(generics.ListAPIView):
    """GET /orders/ — история заказов пользователя"""
    serializer_class = OrderListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()
        queryset = (
            Order.objects.filter(user=self.request.user)
            .select_related('delivery_method_ref')
            .annotate(items_count=Count('items'))
            .order_by('-created_at')
        )
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    @extend_schema(
        tags=['Orders'],
        summary='История заказов пользователя',
        parameters=[
            OpenApiParameter(
                'status',
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                enum=[choice[0] for choice in Order.Status.choices],
            ),
        ],
        responses={200: OrderListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class OrderCreateView(OrderListView):
    """GET /orders/ — история; POST /orders/ — backward-compatible checkout alias"""

    @extend_schema(
        tags=['Orders'],
        summary='Оформить заказ',
        parameters=[CartTokenHeader],
        request=CheckoutSerializer,
        responses={201: OrderSerializer, 400: OpenApiResponse(description='Ошибка оформления заказа')},
    )
    def post(self, request):
        return checkout_response(request)


class OrderDetailView(generics.RetrieveAPIView):
    """GET /orders/<order_number>/"""
    serializer_class = OrderDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'order_number'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()
        return (
            Order.objects.filter(user=self.request.user)
            .select_related('user', 'delivery_method_ref')
            .prefetch_related('items', 'status_history')
        )

    @extend_schema(
        tags=['Orders'],
        summary='Детали заказа по номеру',
        responses={200: OrderDetailSerializer, 404: OpenApiResponse(description='Заказ не найден')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

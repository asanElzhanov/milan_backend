from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import Order, Cart, CartItem
from .serializers import (
    CartSerializer, CartItemAddSerializer,
    OrderSerializer, OrderCreateSerializer,
)
from apps.notifications.tasks import send_order_confirmation_email


def get_or_create_cart(request):
    """Получить корзину — для авторизованного по user, для гостя по session"""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        cart, _ = Cart.objects.get_or_create(
            session_key=request.session.session_key,
            user=None,
        )
    return cart


# ── Корзина ──────────────────────────────────────────────────────────────────

class CartView(APIView):
    """GET /orders/cart/"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cart = get_or_create_cart(request)
        serializer = CartSerializer(cart)
        return Response(serializer.data)


class CartAddView(APIView):
    """POST /orders/cart/add/"""
    permission_classes = [permissions.AllowAny]

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

    def delete(self, request, pk):
        cart = get_or_create_cart(request)
        CartItem.objects.filter(pk=pk, cart=cart).delete()
        return Response(CartSerializer(cart).data)


class CartClearView(APIView):
    """DELETE /orders/cart/clear/"""
    permission_classes = [permissions.AllowAny]

    def delete(self, request):
        cart = get_or_create_cart(request)
        cart.cart_items.all().delete()
        return Response({'detail': 'Корзина очищена'})


# ── Заказы ────────────────────────────────────────────────────────────────────

class OrderCreateView(APIView):
    """POST /orders/ — оформить заказ"""
    permission_classes = [permissions.AllowAny]

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
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class OrderDetailView(generics.RetrieveAPIView):
    """GET /orders/<number>/"""
    serializer_class = OrderSerializer
    lookup_field = 'number'

    def get_permissions(self):
        return [permissions.AllowAny()]

    def get_queryset(self):
        return Order.objects.prefetch_related('items', 'status_history')

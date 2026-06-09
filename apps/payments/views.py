import stripe
import hashlib
import hmac
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from apps.orders.models import Order
from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


PaymentOrderRequestSerializer = inline_serializer(
    name='PaymentOrderRequest',
    fields={'order_number': serializers.CharField()},
)
StripeIntentResponseSerializer = inline_serializer(
    name='StripeIntentResponse',
    fields={'client_secret': serializers.CharField()},
)
KaspiCreateResponseSerializer = inline_serializer(
    name='KaspiCreateResponse',
    fields={'redirect_url': serializers.URLField()},
)
PaymentStatusResponseSerializer = inline_serializer(
    name='PaymentStatusResponse',
    fields={'status': serializers.CharField()},
)
StripeWebhookRequestSerializer = inline_serializer(
    name='StripeWebhookRequest',
    fields={'type': serializers.CharField(), 'data': serializers.JSONField()},
)
KaspiWebhookRequestSerializer = inline_serializer(
    name='KaspiWebhookRequest',
    fields={
        'OrderId': serializers.CharField(),
        'Status': serializers.ChoiceField(choices=['success', 'failed']),
    },
)


class StripeCreateIntentView(APIView):
    """
    POST /payments/stripe/create-intent/
    Body: { "order_number": "ORD-XXXXXXXX" }
    Возвращает client_secret для Stripe Elements на фронте
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / Stripe'],
        summary='Создать Stripe PaymentIntent',
        request=PaymentOrderRequestSerializer,
        responses={
            200: StripeIntentResponseSerializer,
            400: OpenApiResponse(description='Заказ уже оплачен или отменен'),
            404: OpenApiResponse(description='Заказ не найден'),
        },
    )
    def post(self, request):
        order_number = request.data.get('order_number')
        try:
            order = Order.objects.get(number=order_number)
        except Order.DoesNotExist:
            return Response({'detail': 'Заказ не найден'}, status=404)

        if order.status not in (Order.Status.PENDING, Order.Status.CONFIRMED):
            return Response({'detail': 'Заказ уже оплачен или отменён'}, status=400)

        intent = stripe.PaymentIntent.create(
            amount=int(order.total * 100),  # в тиынах / центах
            currency='kzt',
            metadata={'order_number': order.number},
        )

        Payment.objects.update_or_create(
            order=order,
            provider=Payment.Provider.STRIPE,
            defaults={
                'amount': order.total,
                'provider_payment_id': intent.id,
                'status': Payment.Status.PENDING,
            }
        )

        return Response({'client_secret': intent.client_secret})


@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    """
    POST /payments/stripe/webhook/
    Stripe отправляет события сюда
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / Stripe'],
        summary='Stripe webhook',
        request=StripeWebhookRequestSerializer,
        responses={200: PaymentStatusResponseSerializer, 400: OpenApiResponse(description='Некорректная подпись')},
    )
    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.error.SignatureVerificationError):
            return Response(status=400)

        if event['type'] == 'payment_intent.succeeded':
            intent = event['data']['object']
            self._handle_payment_success(intent['id'], intent)

        elif event['type'] == 'payment_intent.payment_failed':
            intent = event['data']['object']
            self._handle_payment_failed(intent['id'])

        return Response({'status': 'ok'})

    def _handle_payment_success(self, provider_id, raw_data):
        payment = Payment.objects.filter(provider_payment_id=provider_id).first()
        if not payment:
            return
        payment.status = Payment.Status.SUCCESS
        payment.provider_data = raw_data
        payment.save()

        order = payment.order
        order.status = Order.Status.PAID
        order.save(update_fields=['status'])

        from apps.orders.models import OrderStatusHistory
        OrderStatusHistory.objects.create(order=order, status=Order.Status.PAID)

        from apps.notifications.tasks import send_order_paid_notification
        send_order_paid_notification.delay(order.id)

    def _handle_payment_failed(self, provider_id):
        Payment.objects.filter(provider_payment_id=provider_id).update(
            status=Payment.Status.FAILED
        )


class KaspiCreateView(APIView):
    """
    POST /payments/kaspi/create/
    Генерируем URL для редиректа в Kaspi Pay
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / Kaspi'],
        summary='Создать ссылку Kaspi Pay',
        request=PaymentOrderRequestSerializer,
        responses={200: KaspiCreateResponseSerializer, 404: OpenApiResponse(description='Заказ не найден')},
    )
    def post(self, request):
        order_number = request.data.get('order_number')
        try:
            order = Order.objects.get(number=order_number)
        except Order.DoesNotExist:
            return Response({'detail': 'Заказ не найден'}, status=404)

        # Kaspi Pay integration URL (упрощённо — реальная интеграция по документации Kaspi)
        merchant_id = settings.KASPI_MERCHANT_ID
        amount = int(order.total)
        redirect_url = f'https://kaspi.kz/online?OrderId={order.number}&Amount={amount}&MerchantId={merchant_id}'

        Payment.objects.update_or_create(
            order=order,
            provider=Payment.Provider.KASPI,
            defaults={
                'amount': order.total,
                'status': Payment.Status.PENDING,
            }
        )

        return Response({'redirect_url': redirect_url})


@method_decorator(csrf_exempt, name='dispatch')
class KaspiWebhookView(APIView):
    """POST /payments/kaspi/webhook/ — коллбэк от Kaspi"""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / Kaspi'],
        summary='Kaspi webhook',
        request=KaspiWebhookRequestSerializer,
        responses={200: PaymentStatusResponseSerializer, 404: OpenApiResponse(description='Заказ не найден')},
    )
    def post(self, request):
        order_number = request.data.get('OrderId')
        tx_status = request.data.get('Status')  # 'success' | 'failed'

        try:
            order = Order.objects.get(number=order_number)
        except Order.DoesNotExist:
            return Response(status=404)

        payment = Payment.objects.filter(order=order, provider=Payment.Provider.KASPI).first()

        if tx_status == 'success':
            if payment:
                payment.status = Payment.Status.SUCCESS
                payment.save()
            order.status = Order.Status.PAID
            order.save(update_fields=['status'])

            from apps.notifications.tasks import send_order_paid_notification
            send_order_paid_notification.delay(order.id)

        elif tx_status == 'failed':
            if payment:
                payment.status = Payment.Status.FAILED
                payment.save()

        return Response({'status': 'ok'})

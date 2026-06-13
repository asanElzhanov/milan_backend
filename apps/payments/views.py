import stripe
import hashlib
import hmac
from django.conf import settings
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers

from apps.orders.models import Order
from apps.orders.services import OrderStatusService
from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


PaymentOrderRequestSerializer = inline_serializer(
    name='PaymentOrderRequest',
    fields={
        'order_number': serializers.CharField(),
        'email': serializers.EmailField(required=False),
    },
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


def delivery_price_not_final_response(order):
    requires_manager = getattr(order, 'delivery_requires_manager_calculation', None)
    if requires_manager is None:
        requires_manager = not order.delivery_price_is_final
    if requires_manager:
        return Response({'detail': 'Стоимость доставки уточняется менеджером'}, status=400)
    return None


def get_order_for_payment(request):
    order_number = request.data.get('order_number')
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return None, Response({'detail': 'Заказ не найден'}, status=404)

    if order.user_id:
        if not request.user.is_authenticated or order.user_id != request.user.id:
            return None, Response({'detail': 'Нет доступа к заказу'}, status=403)
        return order, None

    email = str(request.data.get('email') or '').strip().lower()
    if not email or email != order.email.lower():
        return None, Response({'detail': 'Нет доступа к заказу'}, status=403)
    return order, None


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
        order, error_response = get_order_for_payment(request)
        if error_response is not None:
            return error_response

        if order.status not in (Order.Status.NEW, Order.Status.WAITING_PAYMENT):
            return Response({'detail': 'Заказ уже оплачен или отменён'}, status=400)
        response = delivery_price_not_final_response(order)
        if response is not None:
            return response

        intent = stripe.PaymentIntent.create(
            amount=int(order.total_amount * 100),  # в тиынах / центах
            currency='kzt',
            metadata={'order_number': order.order_number},
        )

        Payment.objects.update_or_create(
            order=order,
            provider=Payment.Provider.STRIPE,
            defaults={
                'amount': order.total_amount,
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

        OrderStatusService.mark_paid(payment.order)

    def _handle_payment_failed(self, provider_id):
        payment = Payment.objects.select_related('order').filter(provider_payment_id=provider_id).first()
        if not payment:
            return
        old_status = payment.status
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=['status', 'updated_at'])
        if old_status != Payment.Status.FAILED:
            from apps.notifications.services import NotificationService

            transaction.on_commit(
                lambda: NotificationService.notify_payment_error(
                    order=payment.order,
                    provider=payment.provider,
                    error_message='Stripe payment failed.',
                )
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
        order, error_response = get_order_for_payment(request)
        if error_response is not None:
            return error_response

        if order.status not in (Order.Status.NEW, Order.Status.WAITING_PAYMENT):
            return Response({'detail': 'Заказ уже оплачен или отменён'}, status=400)
        response = delivery_price_not_final_response(order)
        if response is not None:
            return response

        # Kaspi Pay integration URL (упрощённо — реальная интеграция по документации Kaspi)
        merchant_id = settings.KASPI_MERCHANT_ID
        amount = int(order.total_amount)
        redirect_url = f'https://kaspi.kz/online?OrderId={order.order_number}&Amount={amount}&MerchantId={merchant_id}'

        Payment.objects.update_or_create(
            order=order,
            provider=Payment.Provider.KASPI,
            defaults={
                'amount': order.total_amount,
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
            order = Order.objects.get(order_number=order_number)
        except Order.DoesNotExist:
            return Response(status=404)

        payment = Payment.objects.filter(order=order, provider=Payment.Provider.KASPI).first()

        if tx_status == 'success':
            if payment:
                payment.status = Payment.Status.SUCCESS
                payment.save()
            OrderStatusService.mark_paid(order)

        elif tx_status == 'failed':
            if payment:
                old_status = payment.status
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=['status', 'updated_at'])
                if old_status != Payment.Status.FAILED:
                    from apps.notifications.services import NotificationService

                    transaction.on_commit(
                        lambda: NotificationService.notify_payment_error(
                            order=order,
                            provider=Payment.Provider.KASPI,
                            error_message='Kaspi payment failed.',
                        )
                    )

        return Response({'status': 'ok'})

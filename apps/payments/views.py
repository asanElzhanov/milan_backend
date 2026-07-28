import logging

import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.orders.services import OrderStatusService
from apps.common.statuses import get_status_labels

from . import freedompay
from .models import Payment

logger = logging.getLogger(__name__)


PaymentOrderRequestSerializer = inline_serializer(
    name='PaymentOrderRequest',
    fields={
        'order_number': serializers.CharField(),
        'email': serializers.EmailField(required=False),
        'locale': serializers.CharField(required=False),
        'return_origin': serializers.CharField(required=False),
    },
)
FreedomCreateResponseSerializer = inline_serializer(
    name='FreedomCreateResponse',
    fields={'redirect_url': serializers.URLField()},
)
PaymentStatusResponseSerializer = inline_serializer(
    name='PaymentStatusResponse',
    fields={
        'status': serializers.CharField(),
        'status_labels': serializers.DictField(child=serializers.CharField()),
        'payment_status': serializers.CharField(),
        'payment_status_labels': serializers.DictField(child=serializers.CharField()),
    },
)

SUPPORTED_LOCALES = {'ru', 'kk', 'en'}


def delivery_price_not_final_response(order):
    requires_manager = getattr(order, 'delivery_requires_manager_calculation', None)
    if requires_manager is None:
        requires_manager = not order.delivery_price_is_final
    if requires_manager:
        return Response({'detail': 'Стоимость доставки уточняется менеджером'}, status=400)
    return None


def _check_order_access(order, *, user, email):
    """Общая проверка доступа к заказу (владелец или совпадение email для гостя)."""
    if order.user_id:
        if not user or not user.is_authenticated or order.user_id != user.id:
            return Response({'detail': 'Нет доступа к заказу'}, status=403)
        return None

    email = str(email or '').strip().lower()
    if not email or email != order.email.lower():
        return Response({'detail': 'Нет доступа к заказу'}, status=403)
    return None


def get_order_for_payment(request):
    order_number = request.data.get('order_number')
    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return None, Response({'detail': 'Заказ не найден'}, status=404)

    error = _check_order_access(order, user=request.user, email=request.data.get('email'))
    if error is not None:
        return None, error
    return order, None


def _normalize_locale(value):
    locale = str(value or 'ru').strip().lower()
    return locale if locale in SUPPORTED_LOCALES else 'ru'


def _resolve_frontend_base_url(request):
    """Origin used to build the payment success/fail return URLs.

    The user must return to the *same* origin they started on, because the auth
    session lives in that origin's localStorage. ``localhost`` and ``127.0.0.1``
    (or an apex vs. ``www`` host) are different origins, so a hardcoded
    ``FRONTEND_URL`` can send the user back to an origin where they look logged
    out. Prefer the browser's own origin (explicit ``return_origin`` field or the
    ``Origin`` header) when it is in the trusted allowlist; otherwise fall back to
    the configured ``FRONTEND_URL``.
    """
    default_url = settings.FRONTEND_URL.rstrip('/')
    allowed = {default_url}
    for origin in getattr(settings, 'CORS_ALLOWED_ORIGINS', None) or []:
        allowed.add(str(origin).rstrip('/'))

    candidate = str(request.data.get('return_origin') or '').strip().rstrip('/')
    if not candidate:
        candidate = str(request.headers.get('Origin') or '').strip().rstrip('/')

    if candidate and candidate in allowed:
        return candidate
    return default_url


class FreedomCreatePaymentView(APIView):
    """
    POST /payments/freedom/create/
    Body: { "order_number": "ORD-XXXX", "email"?: "...", "locale"?: "ru" }
    Инициирует платёж в FreedomPay и возвращает ссылку для редиректа.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / FreedomPay'],
        summary='Создать платёж FreedomPay',
        request=PaymentOrderRequestSerializer,
        responses={
            200: FreedomCreateResponseSerializer,
            400: OpenApiResponse(description='Заказ уже оплачен / ошибка инициализации'),
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

        locale = _normalize_locale(request.data.get('locale'))
        backend_url = settings.BACKEND_PUBLIC_URL.rstrip('/')
        frontend_url = _resolve_frontend_base_url(request)
        result_url = f'{backend_url}/api/v1/payments/freedom/result'
        success_url = f'{frontend_url}/{locale}/payment/success'
        failure_url = f'{frontend_url}/{locale}/payment/fail'

        try:
            pg_status, pg_payment_id, redirect_url, raw = freedompay.init_payment(
                order,
                result_url=result_url,
                success_url=success_url,
                failure_url=failure_url,
                locale=locale,
            )
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                'FreedomPay init_payment failed for order %s: %r', order.order_number, exc
            )
            return Response(
                {'detail': f'Не удалось инициировать оплату: {exc}'}, status=400
            )

        if pg_status != 'ok' or not redirect_url:
            logger.warning(
                'FreedomPay rejected init_payment for order %s: status=%s response=%s',
                order.order_number,
                pg_status,
                raw,
            )
            return Response(
                {
                    'detail': raw.get('pg_error_description')
                    or 'FreedomPay отклонил инициализацию платежа'
                },
                status=400,
            )

        Payment.objects.update_or_create(
            order=order,
            provider=Payment.Provider.FREEDOM,
            defaults={
                'amount': order.total_amount,
                'currency': 'KZT',
                'provider_payment_id': pg_payment_id,
                'status': Payment.Status.PENDING,
                'provider_data': raw,
            },
        )

        # Помечаем платёж ожидаемым (payment_status не завязан на машину
        # состояний order.status — его меняем напрямую).
        if order.payment_status in (Order.PaymentStatus.UNPAID, Order.PaymentStatus.FAILED):
            order.payment_status = Order.PaymentStatus.WAITING
            order.save(update_fields=['payment_status', 'updated_at'])

        return Response({'redirect_url': redirect_url})


@method_decorator(csrf_exempt, name='dispatch')
class FreedomResultView(APIView):
    """
    GET/POST /payments/freedom/result
    Серверный callback FreedomPay о результате платежа.
    Отвечает подписанным XML (pg_status=ok|rejected).

    Поддерживаем и POST, и GET: разные магазины FreedomPay шлют result_url
    разными методами.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / FreedomPay'],
        summary='Callback результата оплаты FreedomPay',
        request=None,
        responses={200: OpenApiResponse(description='Подписанный XML-ответ')},
    )
    def post(self, request):
        return self._handle(request, request.data)

    @extend_schema(
        tags=['Payments / FreedomPay'],
        summary='Callback результата оплаты FreedomPay (GET)',
        responses={200: OpenApiResponse(description='Подписанный XML-ответ')},
    )
    def get(self, request):
        return self._handle(request, request.query_params)

    def _handle(self, request, source):
        params = {key: source.get(key) for key in source.keys()}
        logger.info(
            'FreedomPay result callback: method=%s order=%s result=%s params=%s',
            request.method,
            params.get('pg_order_id'),
            params.get('pg_result'),
            params,
        )

        if not freedompay.verify_signature(freedompay.RESULT_SCRIPT, params):
            logger.warning(
                'FreedomPay result callback signature INVALID for order %s',
                params.get('pg_order_id'),
            )
            return self._xml('rejected', 'Invalid signature')

        order_number = params.get('pg_order_id')
        try:
            order = Order.objects.get(order_number=order_number)
        except Order.DoesNotExist:
            logger.warning('FreedomPay result callback: order %s not found', order_number)
            return self._xml('rejected', 'Order not found')

        payment = Payment.objects.filter(
            order=order, provider=Payment.Provider.FREEDOM
        ).first()

        is_success = str(params.get('pg_result')) == '1'

        if is_success:
            if payment and payment.status != Payment.Status.SUCCESS:
                payment.status = Payment.Status.SUCCESS
                payment.provider_data = params
                payment.save(update_fields=['status', 'provider_data', 'updated_at'])
            if order.payment_status != Order.PaymentStatus.PAID:
                OrderStatusService.mark_paid(order)
            logger.info('FreedomPay result callback: order %s marked PAID', order_number)
        else:
            if payment and payment.status != Payment.Status.FAILED:
                payment.status = Payment.Status.FAILED
                payment.provider_data = params
                payment.save(update_fields=['status', 'provider_data', 'updated_at'])

                from apps.notifications.services import NotificationService

                transaction.on_commit(
                    lambda: NotificationService.notify_payment_error(
                        order=order,
                        provider=Payment.Provider.FREEDOM,
                        error_message=params.get('pg_failure_description')
                        or 'FreedomPay payment failed.',
                    )
                )

        return self._xml('ok')

    @staticmethod
    def _xml(status_value, description=''):
        return HttpResponse(
            freedompay.build_result_response(status_value, description),
            content_type='application/xml',
        )


class FreedomStatusView(APIView):
    """
    GET /payments/freedom/status/?order_number=ORD-XXXX&email=...
    Возвращает текущий статус заказа для опроса фронтендом.
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Payments / FreedomPay'],
        summary='Статус оплаты заказа',
        parameters=[
            OpenApiParameter('order_number', str, required=True),
            OpenApiParameter('email', str, required=False),
        ],
        responses={
            200: PaymentStatusResponseSerializer,
            403: OpenApiResponse(description='Нет доступа к заказу'),
            404: OpenApiResponse(description='Заказ не найден'),
        },
    )
    def get(self, request):
        order_number = request.query_params.get('order_number')
        try:
            order = Order.objects.get(order_number=order_number)
        except Order.DoesNotExist:
            return Response({'detail': 'Заказ не найден'}, status=404)

        error = _check_order_access(
            order, user=request.user, email=request.query_params.get('email')
        )
        if error is not None:
            return error

        return Response(
            {
                'status': order.status,
                'status_labels': get_status_labels('order', order.status),
                'payment_status': order.payment_status,
                'payment_status_labels': get_status_labels(
                    'order_payment', order.payment_status,
                ),
            }
        )

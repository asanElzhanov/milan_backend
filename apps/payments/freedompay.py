"""
apps/payments/freedompay.py

Интеграция с FreedomPay (Payment Page / init_payment).

Алгоритм подписи FreedomPay/PayBox:
    md5( script_name; <значения всех pg_-полей без pg_sig, отсортированные по ключу>; secret_key )

script_name — последний сегмент пути URL, который принимает запрос
(для init_payment это 'init_payment.php', для нашего result_url — последний
сегмент его пути).
"""
from __future__ import annotations

import hashlib
import hmac
import xml.etree.ElementTree as ET
from typing import Any

import requests
from django.conf import settings
from django.utils.crypto import get_random_string

# Имя скрипта, которым FreedomPay подписывает ответ init_payment.
INIT_PAYMENT_SCRIPT = 'init_payment.php'
# Последний сегмент пути нашего result_url (см. apps/payments/urls.py -> 'freedom/result').
RESULT_SCRIPT = 'result'

REQUEST_TIMEOUT = 30


def _make_salt() -> str:
    return get_random_string(16)


def generate_signature(script_name: str, params: dict[str, Any], secret_key: str) -> str:
    """Считает pg_sig по правилам FreedomPay."""
    filtered = {k: v for k, v in params.items() if k != 'pg_sig' and v is not None}
    ordered_values = [str(filtered[key]) for key in sorted(filtered)]
    raw = ';'.join([script_name, *ordered_values, secret_key])
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def verify_signature(script_name: str, params: dict[str, Any], secret_key: str | None = None) -> bool:
    """Проверяет pg_sig входящего сообщения (constant-time)."""
    secret_key = secret_key or settings.FREEDOMPAY_SECRET_KEY
    received = str(params.get('pg_sig') or '')
    if not received:
        return False
    expected = generate_signature(script_name, params, secret_key)
    return hmac.compare_digest(received, expected)


def build_signed_params(script_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Добавляет pg_salt и pg_sig к исходящему сообщению."""
    signed = {k: v for k, v in params.items() if v is not None}
    signed.setdefault('pg_salt', _make_salt())
    signed['pg_sig'] = generate_signature(script_name, signed, settings.FREEDOMPAY_SECRET_KEY)
    return signed


def parse_xml_to_dict(xml_text: str) -> dict[str, str]:
    """Разбирает плоский XML-ответ FreedomPay в dict."""
    root = ET.fromstring(xml_text)
    return {child.tag: (child.text or '') for child in root}


def init_payment(order, *, result_url: str, success_url: str, failure_url: str, locale: str = 'ru'):
    """
    Инициирует платёж на стороне FreedomPay.

    Возвращает кортеж (pg_status, pg_payment_id, pg_redirect_url, raw_dict).
    """
    params = build_signed_params(
        INIT_PAYMENT_SCRIPT,
        {
            'pg_merchant_id': settings.FREEDOMPAY_MERCHANT_ID,
            'pg_order_id': order.order_number,
            'pg_amount': str(order.total_amount),
            'pg_currency': 'KZT',
            'pg_description': f'Оплата заказа {order.order_number}',
            'pg_result_url': result_url,
            'pg_success_url': success_url,
            'pg_failure_url': failure_url,
            'pg_success_url_method': 'GET',
            'pg_failure_url_method': 'GET',
            'pg_request_method': 'POST',
            'pg_testing_mode': settings.FREEDOMPAY_TESTING_MODE,
            'pg_language': locale,
            'pg_user_contact_email': order.email,
        },
    )

    response = requests.post(
        f'{settings.FREEDOMPAY_API_URL.rstrip("/")}/{INIT_PAYMENT_SCRIPT}',
        data=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = parse_xml_to_dict(response.text)

    return (
        data.get('pg_status', ''),
        data.get('pg_payment_id', ''),
        data.get('pg_redirect_url', ''),
        data,
    )


def build_result_response(status: str = 'ok', description: str = '') -> str:
    """
    Формирует подписанный XML-ответ на callback result_url.

    status: 'ok' | 'rejected' | 'error'
    """
    params: dict[str, Any] = {
        'pg_salt': _make_salt(),
        'pg_status': status,
    }
    if description:
        params['pg_description'] = description
    params['pg_sig'] = generate_signature(RESULT_SCRIPT, params, settings.FREEDOMPAY_SECRET_KEY)

    root = ET.Element('response')
    for key in ('pg_status', 'pg_description', 'pg_salt', 'pg_sig'):
        if key in params:
            child = ET.SubElement(root, key)
            child.text = str(params[key])
    return ET.tostring(root, encoding='unicode')

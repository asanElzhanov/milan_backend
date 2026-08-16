"""Helpers around Django's ``send_mail`` that make delivery problems visible.

Every outgoing email goes through :func:`send_email_logged` so the logs show
exactly which backend/SMTP host was used, who the recipient was, and what
``send_mail`` reported back. This is what tells you *why* a message never
arrived (console backend, missing SMTP credentials, SMTP error, empty
recipient, ...).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_email_logged(*, subject, message, recipient_list, context='email'):
    """Send an email and log the outcome.

    ``context`` is a short label (e.g. ``'password reset'``) included in every
    log line so different flows can be told apart.

    Returns the number of messages ``send_mail`` reports as sent. Re-raises any
    exception after logging it, so callers/Celery tasks can still retry.
    """
    recipients = [address for address in recipient_list if address]

    if not recipients:
        logger.warning('Email skipped (%s): no recipient address. subject=%r', context, subject)
        return 0

    logger.info(
        'Sending email (%s): to=%s subject=%r via backend=%s host=%s:%s ssl=%s tls=%s from=%s smtp_user=%s',
        context,
        recipients,
        subject,
        settings.EMAIL_BACKEND,
        settings.EMAIL_HOST,
        settings.EMAIL_PORT,
        getattr(settings, 'EMAIL_USE_SSL', False),
        settings.EMAIL_USE_TLS,
        settings.DEFAULT_FROM_EMAIL,
        settings.EMAIL_HOST_USER or '(empty)',
    )

    if settings.EMAIL_BACKEND.endswith('console.EmailBackend'):
        logger.warning(
            'Email (%s) uses the console backend — the message is printed to the '
            'server console and NOT delivered to a real inbox. Set EMAIL_BACKEND '
            'to django.core.mail.backends.smtp.EmailBackend (and EMAIL_HOST_USER/'
            'EMAIL_HOST_PASSWORD) to send real email.',
            context,
        )

    try:
        sent = send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            'Email FAILED (%s): to=%s subject=%r via backend=%s host=%s:%s smtp_user=%s',
            context,
            recipients,
            subject,
            settings.EMAIL_BACKEND,
            settings.EMAIL_HOST,
            settings.EMAIL_PORT,
            settings.EMAIL_HOST_USER or '(empty)',
        )
        raise

    if sent:
        logger.info('Email sent (%s): delivered=%s to=%s subject=%r', context, sent, recipients, subject)
    else:
        logger.warning(
            'Email reported 0 delivered (%s): to=%s subject=%r via backend=%s host=%s — '
            'check SMTP credentials/backend configuration.',
            context,
            recipients,
            subject,
            settings.EMAIL_BACKEND,
            settings.EMAIL_HOST,
        )

    return sent

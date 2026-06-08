import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import OTPCode


OTP_DIGITS = '0123456789'


@dataclass(frozen=True)
class OTPRateLimitResult:
    allowed: bool
    detail: str | None = None


def generate_otp_code(length=6):
    return ''.join(secrets.choice(OTP_DIGITS) for _ in range(length))


def check_otp_request_allowed(user, purpose):
    now = timezone.now()
    cooldown_since = now - timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
    has_recent_request = OTPCode.objects.filter(
        user=user,
        purpose=purpose,
        created_at__gte=cooldown_since,
    ).exists()
    if has_recent_request:
        return OTPRateLimitResult(
            allowed=False,
            detail='Please wait before requesting a new OTP code.',
        )

    hourly_since = now - timedelta(hours=1)
    hourly_count = OTPCode.objects.filter(
        user=user,
        purpose=purpose,
        created_at__gte=hourly_since,
    ).count()
    if hourly_count >= settings.OTP_MAX_ATTEMPTS_PER_HOUR:
        return OTPRateLimitResult(
            allowed=False,
            detail='OTP request limit exceeded. Please try again later.',
        )

    return OTPRateLimitResult(allowed=True)


@transaction.atomic
def create_otp_code(user, purpose):
    OTPCode.objects.filter(
        user=user,
        purpose=purpose,
        is_used=False,
    ).update(is_used=True)

    return OTPCode.objects.create(
        user=user,
        purpose=purpose,
        code=generate_otp_code(),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_CODE_TTL_MINUTES),
        is_used=False,
    )

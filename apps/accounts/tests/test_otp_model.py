from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import OTPCode, User
from apps.accounts.services import generate_otp_code


class OTPCodeModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='otp-model@example.com', password='secret123')

    def test_otp_code_is_created_with_required_fields(self):
        expires_at = timezone.now() + timedelta(minutes=10)

        otp = OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            expires_at=expires_at,
        )

        self.assertEqual(otp.user, self.user)
        self.assertEqual(otp.code, '123456')
        self.assertEqual(otp.purpose, OTPCode.Purpose.EMAIL_VERIFY)
        self.assertEqual(otp.expires_at, expires_at)
        self.assertFalse(otp.is_used)

    def test_email_verify_purpose_is_saved(self):
        otp = OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        self.assertEqual(otp.purpose, OTPCode.Purpose.EMAIL_VERIFY)

    def test_phone_verify_purpose_is_saved(self):
        otp = OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose=OTPCode.Purpose.PHONE_VERIFY,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        self.assertEqual(otp.purpose, OTPCode.Purpose.PHONE_VERIFY)

    def test_is_expired_false_for_active_otp(self):
        otp = OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        self.assertFalse(otp.is_expired)

    def test_is_expired_true_for_expired_otp(self):
        otp = OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertTrue(otp.is_expired)

    def test_mark_used_sets_is_used_true(self):
        otp = OTPCode.objects.create(
            user=self.user,
            code='123456',
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        otp.mark_used()
        otp.refresh_from_db()

        self.assertTrue(otp.is_used)

    def test_code_can_start_with_zero_and_is_stored_as_string(self):
        otp = OTPCode.objects.create(
            user=self.user,
            code='012345',
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        otp.refresh_from_db()

        self.assertEqual(otp.code, '012345')
        self.assertIsInstance(otp.code, str)

    def test_generate_otp_code_uses_secrets_choice_and_preserves_leading_zero(self):
        with patch('apps.accounts.services.secrets.choice', side_effect=list('012345')) as choice:
            code = generate_otp_code()

        self.assertEqual(code, '012345')
        self.assertEqual(choice.call_count, 6)

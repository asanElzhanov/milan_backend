from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import OTPCode, User


@override_settings(
    OTP_CODE_TTL_MINUTES=10,
    OTP_RESEND_COOLDOWN_SECONDS=60,
    OTP_MAX_ATTEMPTS_PER_HOUR=5,
)
class OTPAPITests(APITestCase):
    request_url = '/api/v1/auth/otp/request/'
    verify_url = '/api/v1/auth/otp/verify/'

    def setUp(self):
        self.user = User.objects.create_user(
            email='otp@example.com',
            password='secret123',
            phone='+77000000021',
        )

    def test_authenticated_user_can_request_email_otp_without_code_in_response(self):
        self.client.force_authenticate(self.user)
        before_request = timezone.now()

        with patch('apps.accounts.views.send_otp_task.delay') as send_delay:
            response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.EMAIL_VERIFY}, format='json')

        after_request = timezone.now()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'detail': 'OTP code has been sent.'})
        self.assertNotIn('code', response.data)

        otp = OTPCode.objects.get(user=self.user, purpose=OTPCode.Purpose.EMAIL_VERIFY)
        self.assertFalse(otp.is_used)
        self.assertIsInstance(otp.code, str)
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())
        self.assertGreaterEqual(otp.expires_at, before_request + timedelta(minutes=10) - timedelta(seconds=1))
        self.assertLessEqual(otp.expires_at, after_request + timedelta(minutes=10) + timedelta(seconds=1))
        send_delay.assert_called_once_with(self.user.id, otp.code, OTPCode.Purpose.EMAIL_VERIFY)

    def test_authenticated_user_can_request_phone_otp_via_email_fallback(self):
        self.client.force_authenticate(self.user)

        with patch('apps.accounts.views.send_otp_task.delay') as send_delay:
            response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.PHONE_VERIFY}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        otp = OTPCode.objects.get(user=self.user, purpose=OTPCode.Purpose.PHONE_VERIFY)
        send_delay.assert_called_once_with(self.user.id, otp.code, OTPCode.Purpose.PHONE_VERIFY)

    def test_request_body_user_id_is_ignored(self):
        other_user = User.objects.create_user(email='request-other@example.com', password='secret123')
        self.client.force_authenticate(self.user)

        with patch('apps.accounts.views.send_otp_task.delay'):
            response = self.client.post(
                self.request_url,
                {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'user_id': other_user.id},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(OTPCode.objects.filter(user=self.user).count(), 1)
        self.assertFalse(OTPCode.objects.filter(user=other_user).exists())

    def test_invalid_request_purpose_returns_400(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.request_url, {'purpose': 'password_reset'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_user_cannot_request_or_verify_otp(self):
        request_response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.EMAIL_VERIFY}, format='json')
        verify_response = self.client.post(
            self.verify_url,
            {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': '123456'},
            format='json',
        )

        self.assertEqual(request_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(verify_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cooldown_blocks_request_without_invalidating_existing_otp(self):
        self.client.force_authenticate(self.user)
        active_otp = OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='012345',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.EMAIL_VERIFY}, format='json')

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data, {'detail': 'Please wait before requesting a new OTP code.'})
        active_otp.refresh_from_db()
        self.assertFalse(active_otp.is_used)

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_new_otp_invalidates_old_active_otp(self):
        self.client.force_authenticate(self.user)
        old_otp = OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='012345',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with patch('apps.accounts.views.send_otp_task.delay'):
            response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.EMAIL_VERIFY}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        old_otp.refresh_from_db()
        self.assertTrue(old_otp.is_used)
        self.assertEqual(
            OTPCode.objects.filter(user=self.user, purpose=OTPCode.Purpose.EMAIL_VERIFY, is_used=False).count(),
            1,
        )
        self.assertEqual(
            OTPCode.objects.filter(user=self.user, purpose=OTPCode.Purpose.EMAIL_VERIFY).order_by('-created_at').first().is_used,
            False,
        )

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_hourly_limit_blocks_more_than_five_requests(self):
        self.client.force_authenticate(self.user)
        for index in range(5):
            OTPCode.objects.create(
                user=self.user,
                purpose=OTPCode.Purpose.EMAIL_VERIFY,
                code=f'{index:06d}',
                expires_at=timezone.now() + timedelta(minutes=10),
                is_used=True,
            )

        response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.EMAIL_VERIFY}, format='json')

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data, {'detail': 'OTP request limit exceeded. Please try again later.'})

    def test_verify_email_otp_marks_used_and_verifies_email(self):
        self.client.force_authenticate(self.user)
        otp = OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='012345',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.post(
            self.verify_url,
            {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': '012345'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'detail': 'OTP verified successfully.'})
        self.assertNotIn('code', response.data)
        otp.refresh_from_db()
        self.user.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertTrue(self.user.is_email_verified)
        self.assertTrue(self.user.is_verified)

    def test_repeated_verify_with_same_otp_is_not_allowed(self):
        self.client.force_authenticate(self.user)
        OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='012345',
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        first_response = self.client.post(
            self.verify_url,
            {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': '012345'},
            format='json',
        )
        second_response = self.client.post(
            self.verify_url,
            {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': '012345'},
            format='json',
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second_response.data, {'detail': 'Invalid or expired OTP code.'})

    def test_used_expired_wrong_user_or_invalid_otp_returns_generic_error(self):
        other_user = User.objects.create_user(email='other-otp@example.com', password='secret123')
        OTPCode.objects.create(
            user=other_user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='111111',
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        expired_otp = OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='222222',
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        used_otp = OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='333333',
            expires_at=timezone.now() + timedelta(minutes=10),
            is_used=True,
        )
        self.client.force_authenticate(self.user)

        cases = ['111111', '222222', '333333', '999999']
        for code in cases:
            with self.subTest(code=code):
                response = self.client.post(
                    self.verify_url,
                    {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': code},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data, {'detail': 'Invalid or expired OTP code.'})

        expired_otp.refresh_from_db()
        used_otp.refresh_from_db()
        self.assertTrue(expired_otp.is_used)
        self.assertTrue(used_otp.is_used)

    def test_invalid_verify_purpose_returns_400(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(
            self.verify_url,
            {'purpose': 'password_reset', 'code': '123456'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_code_format_returns_generic_error(self):
        self.client.force_authenticate(self.user)

        for code in ('12345', '1234567', 'abcdef', '12345a'):
            with self.subTest(code=code):
                response = self.client.post(
                    self.verify_url,
                    {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': code},
                    format='json',
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data, {'detail': 'Invalid or expired OTP code.'})

    def test_verify_body_user_id_is_ignored(self):
        other_user = User.objects.create_user(email='verify-other@example.com', password='secret123')
        otp = OTPCode.objects.create(
            user=self.user,
            purpose=OTPCode.Purpose.EMAIL_VERIFY,
            code='012345',
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.client.force_authenticate(self.user)

        response = self.client.post(
            self.verify_url,
            {'purpose': OTPCode.Purpose.EMAIL_VERIFY, 'code': '012345', 'user_id': other_user.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        otp.refresh_from_db()
        other_user.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertFalse(other_user.is_email_verified)

    def test_phone_verify_requires_phone_number(self):
        user = User.objects.create_user(email='no-phone@example.com', password='secret123')
        self.client.force_authenticate(user)

        response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.PHONE_VERIFY}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Phone number is required.')

    def test_verified_email_cannot_request_email_verify_otp(self):
        self.user.is_email_verified = True
        self.user.save(update_fields=['is_email_verified'])
        self.client.force_authenticate(self.user)

        response = self.client.post(self.request_url, {'purpose': OTPCode.Purpose.EMAIL_VERIFY}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Email is already verified.')

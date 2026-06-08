from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
import logging

from .models import User, Address, Wishlist, OTPCode
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer, UserUpdateSerializer,
    ChangePasswordSerializer, AddressSerializer, WishlistSerializer,
    OTPRequestSerializer, OTPVerifySerializer,
)
from .services import check_otp_request_allowed, create_otp_code
from apps.notifications.tasks import send_otp_task


logger = logging.getLogger(__name__)


def _serializer_detail_error(serializer):
    detail = serializer.errors.get('detail')
    if isinstance(detail, list) and detail:
        detail = detail[0]
    if detail:
        return Response({'detail': str(detail)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegisterView(generics.CreateAPIView):
    """POST /auth/register/"""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /auth/login/"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        tokens = serializer.get_tokens(user)
        return Response({
            'user': UserSerializer(user).data,
            'tokens': tokens,
        })


class LogoutView(APIView):
    """POST /auth/logout/ — blacklist refresh token"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data['refresh']
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'detail': 'Выход выполнен'})
        except Exception:
            return Response({'detail': 'Ошибка'}, status=status.HTTP_400_BAD_REQUEST)


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /auth/me/"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserUpdateSerializer
        return UserSerializer


class ChangePasswordView(APIView):
    """POST /auth/change-password/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Пароль изменён'})


class AddressListCreateView(generics.ListCreateAPIView):
    """GET/POST /auth/addresses/"""
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /auth/addresses/<pk>/"""
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class WishlistView(generics.ListAPIView):
    """GET /auth/wishlist/"""
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user).select_related('product')


class WishlistToggleView(APIView):
    """POST /auth/wishlist/toggle/<product_id>/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, product_id):
        item, created = Wishlist.objects.get_or_create(
            user=request.user,
            product_id=product_id,
        )
        if not created:
            item.delete()
            return Response({'status': 'removed'})
        return Response({'status': 'added'}, status=status.HTTP_201_CREATED)


class OTPRequestView(APIView):
    """POST /auth/otp/request/ - send an OTP code."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return _serializer_detail_error(serializer)
        purpose = serializer.validated_data['purpose']

        rate_limit = check_otp_request_allowed(request.user, purpose)
        if not rate_limit.allowed:
            return Response({'detail': rate_limit.detail}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        otp = create_otp_code(request.user, purpose)
        try:
            send_otp_task.delay(request.user.id, otp.code, purpose)
        except Exception:
            logger.exception('Failed to enqueue OTP delivery for user_id=%s', request.user.id)

        return Response({'detail': 'OTP code has been sent.'})


class OTPVerifyView(APIView):
    """POST /auth/otp/verify/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            if 'code' in serializer.errors:
                return Response(
                    {'detail': 'Invalid or expired OTP code.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return _serializer_detail_error(serializer)
        purpose = serializer.validated_data['purpose']
        code = serializer.validated_data['code']
        error_response = Response(
            {'detail': 'Invalid or expired OTP code.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

        otp = OTPCode.objects.filter(
            user=request.user,
            purpose=purpose,
            code=code,
            is_used=False,
        ).order_by('-created_at').first()
        if not otp:
            return error_response

        if otp.is_expired:
            otp.mark_used()
            return error_response

        otp.mark_used()

        if otp.purpose == OTPCode.Purpose.EMAIL_VERIFY:
            request.user.is_email_verified = True
            request.user.save(update_fields=['is_email_verified'])
        elif otp.purpose == OTPCode.Purpose.PHONE_VERIFY:
            # TODO: set is_phone_verified=True here when the User model supports it.
            pass

        return Response({'detail': 'OTP verified successfully.'})

from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from datetime import timedelta
import random

from .models import User, Address, Wishlist, OTPCode
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer, UserUpdateSerializer,
    ChangePasswordSerializer, AddressSerializer, WishlistSerializer,
    OTPRequestSerializer, OTPVerifySerializer,
)


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
    """POST /auth/otp/request/ — отправить код"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purpose = serializer.validated_data['purpose']

        code = str(random.randint(100000, 999999))
        OTPCode.objects.create(
            user=request.user,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        # TODO: отправить через Celery — send_otp_task.delay(request.user.id, code, purpose)
        return Response({'detail': 'Код отправлен'})


class OTPVerifyView(APIView):
    """POST /auth/otp/verify/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data['otp']
        otp.is_used = True
        otp.save()

        if otp.purpose == OTPCode.Purpose.EMAIL_VERIFY:
            request.user.is_email_verified = True
            request.user.save(update_fields=['is_email_verified'])

        return Response({'detail': 'Верификация успешна'})

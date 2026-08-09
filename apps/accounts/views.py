from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema, inline_serializer
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
import logging

from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User, Address, Wishlist, OTPCode
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer, UserUpdateSerializer,
    ChangePasswordSerializer, AddressSerializer, WishlistSerializer,
    OTPRequestSerializer, OTPVerifySerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
)
from .services import check_otp_request_allowed, create_otp_code
from apps.notifications.tasks import send_otp_task, send_password_reset_email
from apps.catalog.models import Product


logger = logging.getLogger(__name__)


AuthTokensSerializer = inline_serializer(
    name='AuthTokens',
    fields={
        'refresh': serializers.CharField(),
        'access': serializers.CharField(),
    },
)
AuthResponseSerializer = inline_serializer(
    name='AuthResponse',
    fields={
        'user': UserSerializer(),
        'tokens': AuthTokensSerializer,
    },
)
DetailResponseSerializer = inline_serializer(
    name='DetailResponse',
    fields={'detail': serializers.CharField()},
)
StatusResponseSerializer = inline_serializer(
    name='StatusResponse',
    fields={'status': serializers.CharField()},
)
LogoutSerializer = inline_serializer(
    name='LogoutRequest',
    fields={'refresh': serializers.CharField()},
)


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

    @extend_schema(
        tags=['Auth'],
        summary='Регистрация пользователя',
        request=RegisterSerializer,
        responses={201: AuthResponseSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
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

    @extend_schema(
        tags=['Auth'],
        summary='Вход пользователя',
        request=LoginSerializer,
        responses={200: AuthResponseSerializer, 400: OpenApiResponse(description='Неверные учетные данные')},
    )
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

    @extend_schema(
        tags=['Auth'],
        summary='Выход пользователя',
        request=LogoutSerializer,
        responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
    )
    def post(self, request):
        try:
            refresh_token = request.data['refresh']
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'detail': 'Выход выполнен'})
        except Exception:
            return Response({'detail': 'Ошибка'}, status=status.HTTP_400_BAD_REQUEST)


class TokenRefreshAPIView(TokenRefreshView):
    @extend_schema(
        tags=['Auth'],
        summary='Обновить JWT access token',
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiResponse(description='Refresh token недействителен')},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /auth/me/"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    @extend_schema(
        tags=['Profile'],
        summary='Получить профиль',
        responses={200: UserSerializer},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['Profile'],
        summary='Обновить профиль',
        request=UserUpdateSerializer,
        responses={200: UserSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=['Profile'],
        summary='Полностью обновить профиль',
        request=UserUpdateSerializer,
        responses={200: UserSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """POST /auth/change-password/"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Profile'],
        summary='Сменить пароль',
        request=ChangePasswordSerializer,
        responses={200: DetailResponseSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Пароль изменён'})


class PasswordResetRequestView(APIView):
    """POST /auth/password-reset/request/ — send a reset link by email."""
    permission_classes = [permissions.AllowAny]

    # Neutral response that never reveals whether an account exists.
    _generic_detail = 'Если аккаунт с такими данными существует, мы отправили ссылку для восстановления пароля.'

    @extend_schema(
        tags=['Auth'],
        summary='Запросить восстановление пароля',
        request=PasswordResetRequestSerializer,
        responses={200: DetailResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.get_user()

        if user is not None and user.email:
            locale = (serializer.validated_data.get('locale') or 'ru').strip() or 'ru'
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = (
                f'{settings.FRONTEND_URL.rstrip("/")}/{locale}/reset-password'
                f'?uid={uid}&token={token}'
            )
            try:
                send_password_reset_email.delay(user.id, reset_url)
            except Exception:
                logger.exception('Failed to enqueue password reset email for user_id=%s', user.id)

        return Response({'detail': self._generic_detail})


class PasswordResetConfirmView(APIView):
    """POST /auth/password-reset/confirm/ — set a new password using a token."""
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=['Auth'],
        summary='Подтвердить восстановление пароля',
        request=PasswordResetConfirmSerializer,
        responses={200: DetailResponseSerializer, 400: OpenApiResponse(description='Ссылка недействительна')},
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'detail': 'Пароль изменён'})


class AddressListCreateView(generics.ListCreateAPIView):
    """GET/POST /auth/addresses/"""
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user).order_by('-is_default', '-created_at', '-id')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        tags=['Addresses'],
        summary='Список адресов',
        responses={200: AddressSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['Addresses'],
        summary='Создать адрес',
        request=AddressSerializer,
        responses={201: AddressSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /auth/addresses/<pk>/"""
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        user = instance.user
        was_default = instance.is_default
        instance.delete()
        if was_default:
            replacement = Address.objects.filter(user=user).order_by('-created_at', '-id').first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=['is_default', 'updated_at'])

    @extend_schema(
        tags=['Addresses'],
        summary='Получить адрес',
        responses={200: AddressSerializer, 404: OpenApiResponse(description='Адрес не найден')},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=['Addresses'],
        summary='Обновить адрес',
        request=AddressSerializer,
        responses={200: AddressSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(
        tags=['Addresses'],
        summary='Полностью обновить адрес',
        request=AddressSerializer,
        responses={200: AddressSerializer, 400: OpenApiResponse(description='Ошибка валидации')},
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        tags=['Addresses'],
        summary='Удалить адрес',
        responses={204: OpenApiResponse(description='Адрес удален')},
    )
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


class WishlistView(generics.ListAPIView):
    """GET /auth/wishlist/"""
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Wishlist.objects.none()
        return Wishlist.objects.filter(user=self.request.user).select_related('product')

    @extend_schema(
        tags=['Wishlist'],
        summary='Список избранного',
        responses={200: WishlistSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class WishlistToggleView(APIView):
    """POST /auth/wishlist/toggle/<product_id>/"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['Wishlist'],
        summary='Добавить или убрать товар из избранного',
        request=None,
        responses={200: StatusResponseSerializer, 201: StatusResponseSerializer},
    )
    def post(self, request, product_id):
        from apps.recommendations.constants import EventSource, EventType, RecommendationContext
        from apps.recommendations.services import RecommendationEventService

        product = get_object_or_404(Product.objects.filter(is_active=True), pk=product_id)
        with transaction.atomic():
            item = Wishlist.objects.select_for_update().filter(
                user=request.user,
                product=product,
            ).first()
            if item is not None:
                item_id = item.id
                RecommendationEventService.record_business_event(
                    event_type=EventType.FAVORITE_REMOVE,
                    source=EventSource.WISHLIST,
                    user=request.user,
                    product=product,
                    context=RecommendationContext.HOME,
                    deduplication_key=f'favorite_remove:{item_id}',
                )
                item.delete()
                return Response({'status': 'removed'})
            item = Wishlist.objects.create(user=request.user, product=product)
            RecommendationEventService.record_business_event(
                event_type=EventType.FAVORITE_ADD,
                source=EventSource.WISHLIST,
                user=request.user,
                product=product,
                context=RecommendationContext.HOME,
                deduplication_key=f'favorite_add:{item.id}',
            )
        return Response({'status': 'added'}, status=status.HTTP_201_CREATED)


class OTPRequestView(APIView):
    """POST /auth/otp/request/ - send an OTP code."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=['OTP'],
        summary='Запросить OTP код',
        request=OTPRequestSerializer,
        responses={200: DetailResponseSerializer, 400: DetailResponseSerializer, 429: DetailResponseSerializer},
    )
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

    @extend_schema(
        tags=['OTP'],
        summary='Подтвердить OTP код',
        request=OTPVerifySerializer,
        responses={200: DetailResponseSerializer, 400: DetailResponseSerializer},
    )
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

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from .models import User, Address, Wishlist, OTPCode


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('email', 'phone', 'first_name', 'last_name', 'password', 'password2')

    def validate(self, data):
        if data['password'] != data.pop('password2'):
            raise serializers.ValidationError({'password2': 'Пароли не совпадают'})
        return data

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(email=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError('Неверный email или пароль')
        if not user.is_active:
            raise serializers.ValidationError('Аккаунт заблокирован')
        data['user'] = user
        return data

    def get_tokens(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    is_verified = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'phone', 'first_name', 'last_name',
            'full_name', 'role', 'is_verified',
        )
        read_only_fields = ('id', 'email', 'role', 'is_verified')


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'phone', 'avatar')


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Старый пароль неверен')
        return value

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ('id', 'title', 'country', 'city', 'street', 'apartment', 'postal_code', 'is_default')


class WishlistSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = Wishlist
        fields = ('id', 'product', 'added_at')

    def get_product(self, obj):
        from apps.catalog.serializers import ProductListSerializer
        return ProductListSerializer(obj.product).data


class OTPRequestSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=OTPCode.Purpose.choices)


class OTPVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6)
    purpose = serializers.ChoiceField(choices=OTPCode.Purpose.choices)

    def validate(self, data):
        user = self.context['request'].user
        otp = OTPCode.objects.filter(
            user=user,
            code=data['code'],
            purpose=data['purpose'],
            is_used=False,
            expires_at__gt=timezone.now()
        ).first()
        if not otp:
            raise serializers.ValidationError('Неверный или истёкший код')
        data['otp'] = otp
        return data

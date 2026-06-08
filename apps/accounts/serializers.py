from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
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


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    is_verified = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'phone', 'first_name', 'last_name',
            'full_name', 'avatar', 'role', 'is_verified', 'date_joined',
        )
        read_only_fields = ('id', 'email', 'full_name', 'role', 'is_verified', 'date_joined')


UserSerializer = UserProfileSerializer
UserUpdateSerializer = UserProfileSerializer


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
        fields = (
            'id', 'title', 'country', 'city', 'street', 'apartment',
            'postal_code', 'is_default', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class WishlistSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = Wishlist
        fields = ('id', 'product', 'added_at')

    def get_product(self, obj):
        from apps.catalog.serializers import ProductListSerializer
        return ProductListSerializer(obj.product).data


SUPPORTED_OTP_PURPOSES = (
    OTPCode.Purpose.EMAIL_VERIFY,
    OTPCode.Purpose.PHONE_VERIFY,
)


class OTPRequestSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=SUPPORTED_OTP_PURPOSES)

    def validate(self, data):
        user = self.context['request'].user
        purpose = data['purpose']
        if purpose == OTPCode.Purpose.EMAIL_VERIFY:
            if not user.email:
                raise serializers.ValidationError({'detail': 'Email is required.'})
            if user.is_email_verified:
                raise serializers.ValidationError({'detail': 'Email is already verified.'})
        if purpose == OTPCode.Purpose.PHONE_VERIFY and not user.phone:
            raise serializers.ValidationError({'detail': 'Phone number is required.'})
        return data


class OTPVerifySerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=SUPPORTED_OTP_PURPOSES)
    code = serializers.RegexField(
        regex=r'^\d{6}$',
        max_length=6,
        min_length=6,
        error_messages={'invalid': 'Invalid or expired OTP code.'},
    )

    def validate(self, data):
        return data

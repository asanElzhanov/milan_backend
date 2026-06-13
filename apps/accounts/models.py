from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('Email is required'))
        email = self.normalize_email(email)
        extra_fields.setdefault('role', User.Role.CUSTOMER)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        MANAGER = 'manager', 'Manager'
        ADMIN = 'admin', 'Admin'

    email = models.EmailField(_('email'), unique=True)
    phone = PhoneNumberField(_('телефон'), blank=True, null=True, unique=True)
    first_name = models.CharField(_('имя'), max_length=100, blank=True)
    last_name = models.CharField(_('фамилия'), max_length=100, blank=True)
    avatar = models.ImageField(_('фото'), upload_to='avatars/', blank=True, null=True)
    role = models.CharField('role', max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('пользователь')
        verbose_name_plural = _('пользователи')
        ordering = ['-date_joined']

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def is_verified(self) -> bool:
        return self.is_email_verified

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN


class Address(models.Model):
    """Адрес доставки пользователя"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    title = models.CharField(_('название'), max_length=100, blank=True, help_text='Дом, Работа...')
    country = models.CharField(_('страна'), max_length=100, default='Казахстан')
    city = models.CharField(_('город'), max_length=100)
    street = models.CharField(_('улица'), max_length=255)
    apartment = models.CharField(_('квартира/офис'), max_length=50, blank=True)
    postal_code = models.CharField(_('индекс'), max_length=20, blank=True)
    is_default = models.BooleanField(_('по умолчанию'), default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('адрес')
        verbose_name_plural = _('адреса')

    def __str__(self):
        return f'{self.title} - {self.city}, {self.street}' if self.title else f'{self.city}, {self.street}'

    def save(self, *args, **kwargs):
        if not self.pk and not Address.objects.filter(user=self.user).exists():
            self.is_default = True
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class CustomerProfile(models.Model):
    class Source(models.TextChoices):
        WEBSITE = 'website', _('Website')
        INSTAGRAM = 'instagram', _('Instagram')
        WHATSAPP = 'whatsapp', _('WhatsApp')
        REFERRAL = 'referral', _('Referral')
        MARKETPLACE = 'marketplace', _('Marketplace')
        OFFLINE = 'offline', _('Offline')
        OTHER = 'other', _('Other')

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile',
        verbose_name=_('пользователь'),
    )
    source = models.CharField(
        _('источник клиента'),
        max_length=20,
        choices=Source.choices,
        default=Source.WEBSITE,
    )
    manager_comment = models.TextField(_('комментарий менеджера'), blank=True)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлен'), auto_now=True)

    class Meta:
        verbose_name = _('профиль клиента')
        verbose_name_plural = _('профили клиентов')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return str(self.user)


@receiver(post_save, sender=User)
def create_customer_profile(sender, instance, **kwargs):
    if instance.role == User.Role.CUSTOMER:
        CustomerProfile.objects.get_or_create(user=instance)


class Wishlist(models.Model):
    """Избранное"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('избранное')
        verbose_name_plural = _('избранное')
        unique_together = ('user', 'product')


class OTPCode(models.Model):
    """Одноразовый код для верификации телефона / email"""
    class Purpose(models.TextChoices):
        PHONE_VERIFY = 'phone_verify', 'Верификация телефона'
        EMAIL_VERIFY = 'email_verify', 'Верификация email'
        PASSWORD_RESET = 'password_reset', 'Сброс пароля'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('OTP код')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} - {self.code}'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_used(self):
        self.is_used = True
        self.save(update_fields=['is_used'])



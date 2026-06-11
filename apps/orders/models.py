from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', _('Новый')
        WAITING_PAYMENT = 'waiting_payment', _('Ожидает оплаты')
        PAID = 'paid', _('Оплачен')
        PROCESSING = 'processing', _('В обработке')
        SHIPPED = 'shipped', _('Отправлен')
        COMPLETED = 'completed', _('Завершён')
        CANCELLED = 'cancelled', _('Отменён')
        RETURNED = 'returned', _('Возврат')

    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', _('Не оплачен')
        WAITING = 'waiting', _('Ожидает оплаты')
        PAID = 'paid', _('Оплачен')
        FAILED = 'failed', _('Ошибка оплаты')
        REFUNDED = 'refunded', _('Возвращён')
        CANCELLED = 'cancelled', _('Отменён')

    class DeliveryMethod(models.TextChoices):
        COURIER = 'courier', _('Курьер')
        PICKUP = 'pickup', _('Самовывоз')
        POST = 'post', _('Почта')
        OTHER = 'other', _('Другое')

    order_number = models.CharField(_('номер заказа'), max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders'
    )
    customer_name = models.CharField(_('имя покупателя'), max_length=255)
    phone = models.CharField(_('телефон'), max_length=30)
    email = models.EmailField(_('email'))
    city = models.CharField(_('город'), max_length=100, blank=True)
    delivery_address = models.TextField(blank=True)
    delivery_method = models.CharField(max_length=20, choices=DeliveryMethod.choices)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('заказ')
        verbose_name_plural = _('заказы')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['user']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['phone']),
            models.Index(fields=['email']),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(total_amount__gte=0),
                name='order_total_amount_non_negative',
            ),
        ]

    def __str__(self):
        return f'Заказ #{self.order_number}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_order_number(cls):
        while True:
            order_number = 'ORD-' + get_random_string(8, '0123456789ABCDEF')
            if not cls.objects.filter(order_number=order_number).exists():
                return order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='order_items',
    )
    product_name = models.CharField(max_length=255)
    product_slug = models.SlugField(max_length=280)
    sku = models.CharField(max_length=100)
    size_name = models.CharField(max_length=50, blank=True)
    color_name = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )

    class Meta:
        verbose_name = _('позиция заказа')
        verbose_name_plural = _('позиции заказа')
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                check=Q(quantity__gt=0),
                name='order_item_quantity_positive',
            ),
            models.CheckConstraint(
                check=Q(unit_price__gte=0),
                name='order_item_unit_price_non_negative',
            ),
            models.CheckConstraint(
                check=Q(total_price__gte=0),
                name='order_item_total_price_non_negative',
            ),
        ]

    def __str__(self):
        return f'{self.product_name} x{self.quantity}'

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    """История изменений статуса заказа"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class Cart(models.Model):
    """Корзина пользователя или гостя."""
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='carts',
    )
    token = models.UUIDField(
        _('guest cart token'),
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        default=uuid.uuid4,
    )
    is_active = models.BooleanField(_('активна'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('корзина')
        verbose_name_plural = _('корзины')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['token']),
            models.Index(fields=['is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(user__isnull=False, is_active=True),
                name='unique_active_cart_per_user',
            ),
        ]

    def __str__(self):
        owner = self.user or self.token
        return f'Корзина {owner}'

    @property
    def total(self) -> Decimal:
        return sum(item.total_price for item in self.items.all())

    @property
    def items_count(self) -> int:
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.CASCADE,
        related_name='cart_items',
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('позиция корзины')
        verbose_name_plural = _('позиции корзины')
        indexes = [
            models.Index(fields=['cart']),
            models.Index(fields=['variant']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['cart', 'variant'], name='unique_cart_variant'),
            models.CheckConstraint(check=Q(quantity__gt=0), name='cart_item_quantity_positive'),
        ]

    def __str__(self):
        return f'{self.variant} x{self.quantity}'

    def clean(self):
        super().clean()
        if self.variant_id and not self.variant.is_active:
            raise ValidationError({'variant': _('Вариант товара неактивен.')})
        if self.variant_id and not self.variant.product.is_active:
            raise ValidationError({'variant': _('Товар неактивен.')})

    @property
    def total_price(self) -> Decimal:
        return self.variant.final_price * self.quantity

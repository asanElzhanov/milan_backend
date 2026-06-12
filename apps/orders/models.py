from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils.text import slugify
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
        KAZAKHSTAN_DELIVERY = 'kazakhstan_delivery', _('Доставка по Казахстану')
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
    delivery_method = models.CharField(max_length=50, choices=DeliveryMethod.choices)
    delivery_method_ref = models.ForeignKey(
        'DeliveryMethod',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name=_('способ доставки'),
    )
    delivery_method_code = models.CharField(_('код способа доставки'), max_length=50, blank=True)
    delivery_method_name = models.CharField(_('название способа доставки'), max_length=120, blank=True)
    items_total = models.DecimalField(
        _('сумма товаров'),
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    delivery_price = models.DecimalField(
        _('стоимость доставки'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    delivery_requires_manager_calculation = models.BooleanField(
        _('стоимость доставки требует расчета менеджером'),
        default=False,
    )
    delivery_price_is_final = models.BooleanField(_('стоимость доставки финальная'), default=True)
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
            models.Index(fields=['delivery_method_ref'], name='orders_orde_deliver_186dd8_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(total_amount__gte=0),
                name='order_total_amount_non_negative',
            ),
            models.CheckConstraint(
                check=Q(delivery_price__gte=0),
                name='order_delivery_price_non_negative',
            ),
            models.CheckConstraint(
                check=Q(items_total__gte=0),
                name='order_items_total_non_negative',
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


class DeliveryMethod(models.Model):
    class DeliveryType(models.TextChoices):
        COURIER = 'courier', _('Курьер')
        PICKUP = 'pickup', _('Самовывоз')
        KAZAKHSTAN_DELIVERY = 'kazakhstan_delivery', _('Доставка по Казахстану')

    class PriceType(models.TextChoices):
        FIXED = 'fixed', _('Фиксированная')
        MANAGER_CALCULATION = 'manager_calculation', _('Уточняется менеджером')
        FREE = 'free', _('Бесплатная')

    name = models.CharField(_('название'), max_length=120)
    code = models.CharField(_('код'), max_length=50, unique=True)
    slug = models.SlugField(_('slug'), max_length=80, unique=True)
    delivery_type = models.CharField(
        _('тип доставки'),
        max_length=32,
        choices=DeliveryType.choices,
    )
    description = models.TextField(_('описание'), blank=True)
    is_active = models.BooleanField(_('активен'), default=True)
    base_price = models.DecimalField(
        _('базовая цена'),
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    price_type = models.CharField(
        _('тип цены'),
        max_length=32,
        choices=PriceType.choices,
        default=PriceType.FIXED,
    )
    free_from_amount = models.DecimalField(
        _('бесплатно от суммы'),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    sort_order = models.PositiveSmallIntegerField(_('порядок'), default=0)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлен'), auto_now=True)

    class Meta:
        verbose_name = _('способ доставки')
        verbose_name_plural = _('способы доставки')
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['code'], name='orders_deli_code_e26177_idx'),
            models.Index(fields=['slug'], name='orders_deli_slug_73500e_idx'),
            models.Index(fields=['is_active'], name='orders_deli_is_acti_05610c_idx'),
            models.Index(fields=['delivery_type'], name='orders_deli_deliver_d26c22_idx'),
            models.Index(fields=['sort_order'], name='orders_deli_sort_or_0b8728_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(base_price__gte=0),
                name='delivery_method_base_price_non_negative',
            ),
            models.CheckConstraint(
                check=Q(free_from_amount__isnull=True) | Q(free_from_amount__gte=0),
                name='delivery_method_free_from_amount_non_negative',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


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
    old_status = models.CharField(
        max_length=20,
        choices=Order.Status.choices,
        null=True,
        blank=True,
    )
    new_status = models.CharField(max_length=20, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_status_changes',
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order']),
            models.Index(fields=['old_status']),
            models.Index(fields=['new_status']),
            models.Index(fields=['changed_by']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        old_status = self.old_status or 'initial'
        return f'{self.order.order_number}: {old_status} -> {self.new_status}'


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

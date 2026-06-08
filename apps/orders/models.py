from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Ожидает подтверждения')
        CONFIRMED = 'confirmed', _('Подтверждён')
        PAID = 'paid', _('Оплачен')
        PROCESSING = 'processing', _('В обработке')
        SHIPPED = 'shipped', _('Отправлен')
        DELIVERED = 'delivered', _('Доставлен')
        CANCELLED = 'cancelled', _('Отменён')
        REFUNDED = 'refunded', _('Возврат')

    class DeliveryMethod(models.TextChoices):
        COURIER = 'courier', _('Курьер')
        PICKUP = 'pickup', _('Самовывоз')
        KAZPOST = 'kazpost', _('Казпочта')
        DHL = 'dhl', _('DHL International')

    number = models.CharField(_('номер заказа'), max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders'
    )

    # Контакт
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    comment = models.TextField(blank=True)

    # Доставка
    delivery_method = models.CharField(max_length=20, choices=DeliveryMethod.choices)
    delivery_address = models.TextField(blank=True)
    delivery_city = models.CharField(max_length=100, blank=True)
    delivery_country = models.CharField(max_length=100, default='Казахстан')
    delivery_postal_code = models.CharField(max_length=20, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)

    # Суммы
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    # Промокод
    promo_code = models.CharField(max_length=50, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('заказ')
        verbose_name_plural = _('заказы')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['number']),
        ]

    def __str__(self):
        return f'Заказ #{self.number}'

    def save(self, *args, **kwargs):
        if not self.number:
            # Генерация уникального номера
            from django.utils.crypto import get_random_string
            self.number = 'ORD-' + get_random_string(8, '0123456789ABCDEF')
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('catalog.Product', on_delete=models.SET_NULL, null=True)
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.SET_NULL, null=True)

    # Снапшот данных на момент заказа
    product_name = models.CharField(max_length=255)
    product_sku = models.CharField(max_length=100, blank=True)
    color_name = models.CharField(max_length=50, blank=True)
    size_value = models.CharField(max_length=20, blank=True)

    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _('позиция заказа')

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
    """Корзина — для гостей по session_key, для пользователей по user"""
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, null=True, blank=True, related_name='cart'
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('корзина')

    def __str__(self):
        return f'Корзина {self.user or self.session_key}'

    @property
    def total(self):
        return sum(item.total_price for item in self.cart_items.all())

    @property
    def items_count(self):
        return sum(item.quantity for item in self.cart_items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='cart_items')
    variant = models.ForeignKey('catalog.ProductVariant', on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'variant')
        verbose_name = _('позиция корзины')

    def __str__(self):
        return f'{self.variant} x{self.quantity}'

    @property
    def total_price(self):
        return self.variant.final_price * self.quantity

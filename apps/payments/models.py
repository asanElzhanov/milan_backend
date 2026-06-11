"""
apps/payments/models.py
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Ожидает')
        SUCCESS = 'success', _('Успешно')
        FAILED = 'failed', _('Ошибка')
        REFUNDED = 'refunded', _('Возврат')

    class Provider(models.TextChoices):
        STRIPE = 'stripe', 'Stripe'
        KASPI = 'kaspi', 'Kaspi Pay'
        FREEDOM = 'freedom', 'Freedom Pay'
        COD = 'cod', _('Наличными при получении')

    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(max_length=20, choices=Provider.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='KZT')

    # Внешние идентификаторы провайдера
    provider_payment_id = models.CharField(max_length=255, blank=True)
    provider_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('платёж')
        verbose_name_plural = _('платежи')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order.order_number} — {self.provider} — {self.status}'

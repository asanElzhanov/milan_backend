from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = 'customer', _('Customer')
        MANAGER = 'manager', _('Manager')
        ADMIN = 'admin', _('Admin')
        STAFF = 'staff', _('Staff')

    class EventType(models.TextChoices):
        ORDER_CREATED = 'order_created', _('Order created')
        ORDER_PAID = 'order_paid', _('Order paid')
        ORDER_STATUS_CHANGED = 'order_status_changed', _('Order status changed')
        ORDER_CANCELLED = 'order_cancelled', _('Order cancelled')
        PAYMENT_SUCCESS = 'payment_success', _('Payment success')
        PAYMENT_ERROR = 'payment_error', _('Payment error')
        REVIEW_CREATED = 'review_created', _('Review created')
        REVIEW_PUBLISHED = 'review_published', _('Review published')
        REVIEW_REJECTED = 'review_rejected', _('Review rejected')
        LOW_STOCK = 'low_stock', _('Low stock')
        IMPORT_ERROR = 'import_error', _('Import error')
        SYSTEM = 'system', _('System')

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name=_('recipient'),
    )
    role = models.CharField(
        _('role'),
        max_length=20,
        choices=Role.choices,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('уведомление')
        verbose_name_plural = _('уведомления')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient']),
            models.Index(fields=['role']),
            models.Index(fields=['event_type']),
            models.Index(fields=['is_read']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        target = self.recipient or self.role or _('all')
        return f'{self.title} -> {target}'

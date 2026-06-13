from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import (
    Cart, DeliveryMethod, Order, OrderItem, OrderStatusHistory,
    PromoCode, PromoCodeUsage,
)
from .services import OrderStatusService


class OrderAdminForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = '__all__'

    def clean_status(self):
        status = self.cleaned_data['status']
        if not self.instance.pk or status == self.instance.status:
            return status

        old_status = self.instance.status
        if status == Order.Status.CANCELLED:
            if old_status not in OrderStatusService.cancellable_statuses:
                raise ValidationError(f'Нельзя отменить заказ из статуса {old_status}.')
            return status
        if status == Order.Status.PAID:
            if old_status not in {Order.Status.NEW, Order.Status.WAITING_PAYMENT, Order.Status.PAID}:
                raise ValidationError(f'Нельзя отметить оплаченным заказ из статуса {old_status}.')
            return status
        if status not in OrderStatusService.allowed_transitions.get(old_status, set()):
            raise ValidationError(f'Недопустимый переход статуса {old_status} -> {status}.')
        return status


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        'product_name', 'product_slug', 'sku', 'size_name', 'color_name',
        'unit_price', 'quantity', 'total_price',
    )
    readonly_fields = (
        'product_name', 'product_slug', 'sku', 'size_name', 'color_name',
        'unit_price', 'quantity', 'total_price',
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ('old_status', 'new_status', 'changed_by', 'comment', 'created_at')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    form = OrderAdminForm
    list_display = (
        'order_number', 'customer_name', 'phone', 'email', 'city',
        'total_amount', 'status', 'payment_status',
        'delivery_display', 'created_at',
    )
    search_fields = (
        'order_number', 'phone', 'email', 'customer_name',
        'items__sku', 'items__product_name',
    )
    list_filter = ('status', 'payment_status', 'delivery_method', 'city', 'created_at')
    readonly_fields = (
        'order_number', 'delivery_method_code', 'delivery_method_name',
        'items_total', 'discount_amount', 'delivery_price',
        'delivery_requires_manager_calculation', 'delivery_price_is_final',
        'promo_code', 'promo_code_text', 'total_amount', 'created_at', 'updated_at',
    )
    ordering = ('-created_at',)
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    actions = (
        'mark_as_processing',
        'mark_as_shipped',
        'mark_as_completed',
        'cancel_selected_orders',
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('user', 'delivery_method_ref', 'promo_code')
            .prefetch_related('items', 'status_history')
        )

    @admin.display(description='способ доставки', ordering='delivery_method')
    def delivery_display(self, obj):
        return obj.delivery_method_name or obj.get_delivery_method_display()

    def save_model(self, request, obj, form, change):
        requested_status = obj.status
        status_changed = change and 'status' in form.changed_data
        if not status_changed:
            super().save_model(request, obj, form, change)
            return

        persisted_order = Order.objects.get(pk=obj.pk)
        obj.status = persisted_order.status
        super().save_model(request, obj, form, change)

        try:
            updated_order = self._change_order_status(
                persisted_order,
                requested_status,
                request.user,
                comment=obj.manager_comment or 'Статус изменён через Django Admin',
            )
        except ValidationError as exc:
            obj.status = persisted_order.status
            raise exc
        obj.status = updated_order.status
        obj.payment_status = updated_order.payment_status

    @staticmethod
    def _change_order_status(order, status, user, comment=''):
        if status == Order.Status.CANCELLED:
            return OrderStatusService.cancel_order(order, changed_by=user, comment=comment)
        if status == Order.Status.PAID:
            return OrderStatusService.mark_paid(order, changed_by=user, comment=comment)
        return OrderStatusService.change_status(order, status, changed_by=user, comment=comment)

    def _bulk_change_status(self, request, queryset, status):
        changed = 0
        for order in queryset:
            try:
                self._change_order_status(
                    order,
                    status,
                    request.user,
                    comment='Статус изменён через Django Admin',
                )
            except ValidationError as exc:
                self.message_user(request, f'{order.order_number}: {exc}', level=messages.ERROR)
            else:
                changed += 1
        if changed:
            self.message_user(request, f'Обновлено заказов: {changed}.', level=messages.SUCCESS)

    @admin.action(description='Перевести выбранные заказы в обработку')
    def mark_as_processing(self, request, queryset):
        self._bulk_change_status(request, queryset, Order.Status.PROCESSING)

    @admin.action(description='Отметить выбранные заказы отправленными')
    def mark_as_shipped(self, request, queryset):
        self._bulk_change_status(request, queryset, Order.Status.SHIPPED)

    @admin.action(description='Отметить выбранные заказы завершёнными')
    def mark_as_completed(self, request, queryset):
        self._bulk_change_status(request, queryset, Order.Status.COMPLETED)

    @admin.action(description='Отменить выбранные заказы')
    def cancel_selected_orders(self, request, queryset):
        self._bulk_change_status(request, queryset, Order.Status.CANCELLED)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order', 'product_name', 'sku', 'size_name',
        'color_name', 'unit_price', 'quantity', 'total_price',
    )
    search_fields = ('order__order_number', 'product_name', 'sku')
    list_filter = ('order__status',)
    readonly_fields = (
        'order', 'variant', 'product_name', 'product_slug', 'sku',
        'size_name', 'color_name', 'unit_price', 'quantity', 'total_price',
    )
    ordering = ('id',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'variant')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'old_status', 'new_status', 'changed_by', 'created_at')
    list_filter = ('old_status', 'new_status', 'created_at')
    search_fields = ('order__order_number', 'changed_by__email', 'comment')
    readonly_fields = ('order', 'old_status', 'new_status', 'changed_by', 'comment', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Cart)


class PromoCodeUsageInline(admin.TabularInline):
    model = PromoCodeUsage
    extra = 0
    fields = ('order', 'user', 'created_at')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PromoCodeAdminForm(forms.ModelForm):
    class Meta:
        model = PromoCode
        fields = '__all__'

    def clean_code(self):
        code = self.cleaned_data['code']
        return code.strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        discount_type = cleaned_data.get('discount_type')
        value = cleaned_data.get('value')
        valid_from = cleaned_data.get('valid_from')
        valid_until = cleaned_data.get('valid_until')

        if value is not None and value <= Decimal('0.00'):
            self.add_error('value', 'Значение скидки должно быть больше нуля.')
        if (
            discount_type == PromoCode.DiscountType.PERCENT
            and value is not None
            and value > Decimal('100.00')
        ):
            self.add_error('value', 'Процентная скидка не может быть больше 100%.')
        if (
            discount_type == PromoCode.DiscountType.FIXED
            and value is not None
            and value <= Decimal('0.00')
        ):
            self.add_error('value', 'Фиксированная скидка должна быть больше нуля.')
        if valid_from and valid_until and valid_until < valid_from:
            self.add_error('valid_until', 'Дата окончания не может быть раньше даты начала.')
        return cleaned_data


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    form = PromoCodeAdminForm
    list_display = (
        'code', 'discount_type', 'value', 'min_order_amount',
        'usage_limit', 'used_count', 'remaining_uses',
        'valid_from', 'valid_until', 'is_active',
    )
    list_filter = ('is_active', 'discount_type', 'valid_from', 'valid_until')
    search_fields = ('code',)
    readonly_fields = ('used_count', 'remaining_uses', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    inlines = [PromoCodeUsageInline]

    @admin.display(description='остаток использований')
    def remaining_uses(self, obj):
        if obj.usage_limit is None:
            return 'без лимита'
        return max(obj.usage_limit - obj.used_count, 0)


@admin.register(PromoCodeUsage)
class PromoCodeUsageAdmin(admin.ModelAdmin):
    list_display = ('promo_code', 'order', 'user', 'created_at')
    list_filter = ('created_at', 'promo_code')
    search_fields = ('promo_code__code', 'order__order_number', 'user__email')
    readonly_fields = ('promo_code', 'order', 'user', 'created_at')
    ordering = ('-created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('promo_code', 'order', 'user')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if obj is None:
            return super().has_change_permission(request, obj)
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeliveryMethod)
class DeliveryMethodAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'code', 'delivery_type', 'price_type',
        'base_price', 'free_from_amount', 'is_active', 'sort_order',
    )
    list_filter = ('is_active', 'delivery_type', 'price_type')
    search_fields = ('name', 'code', 'slug')
    list_editable = ('price_type', 'base_price', 'free_from_amount', 'is_active', 'sort_order')
    ordering = ('sort_order', 'name')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

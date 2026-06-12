from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import (
    Cart, DeliveryMethod, Order, OrderItem, OrderStatusHistory,
    PromoCode, PromoCodeUsage,
)
from .services import OrderStatusService


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        'product_name', 'sku', 'size_name', 'color_name',
        'unit_price', 'quantity', 'total_price',
    )
    readonly_fields = (
        'product_name', 'sku', 'size_name', 'color_name',
        'unit_price', 'quantity', 'total_price',
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
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
    list_display = (
        'order_number', 'user', 'customer_name', 'phone', 'city',
        'total_amount', 'delivery_price', 'status', 'payment_status',
        'delivery_method', 'created_at',
    )
    search_fields = (
        'order_number', 'customer_name', 'phone', 'email',
        'items__sku', 'items__product_name',
    )
    list_filter = ('status', 'payment_status', 'delivery_method_ref', 'delivery_method', 'city', 'created_at')
    readonly_fields = (
        'order_number', 'delivery_method_code', 'delivery_method_name',
        'items_total', 'delivery_price', 'delivery_requires_manager_calculation',
        'delivery_price_is_final', 'total_amount', 'created_at', 'updated_at',
    )
    ordering = ('-created_at',)
    inlines = [OrderItemInline, OrderStatusHistoryInline]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('user', 'delivery_method_ref')
            .prefetch_related('items', 'status_history')
        )

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
            if requested_status == Order.Status.CANCELLED:
                updated_order = OrderStatusService.cancel_order(
                    persisted_order,
                    changed_by=request.user,
                    comment='Статус изменён через Django Admin',
                )
            elif requested_status == Order.Status.PAID:
                updated_order = OrderStatusService.mark_paid(
                    persisted_order,
                    changed_by=request.user,
                    comment='Статус изменён через Django Admin',
                )
            else:
                updated_order = OrderStatusService.change_status(
                    persisted_order,
                    requested_status,
                    changed_by=request.user,
                    comment='Статус изменён через Django Admin',
                )
        except ValidationError as exc:
            obj.status = persisted_order.status
            raise exc
        obj.status = updated_order.status
        obj.payment_status = updated_order.payment_status


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


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'discount_type', 'value', 'min_order_amount',
        'used_count', 'usage_limit', 'is_active', 'valid_from', 'valid_until',
    )
    list_filter = ('is_active', 'discount_type', 'valid_from', 'valid_until')
    search_fields = ('code',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


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

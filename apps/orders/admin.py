from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Cart, Order, OrderItem, OrderStatusHistory
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
        'total_amount', 'status', 'payment_status', 'delivery_method', 'created_at',
    )
    search_fields = (
        'order_number', 'customer_name', 'phone', 'email',
        'items__sku', 'items__product_name',
    )
    list_filter = ('status', 'payment_status', 'delivery_method', 'city', 'created_at')
    readonly_fields = ('order_number', 'total_amount', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    inlines = [OrderItemInline, OrderStatusHistoryInline]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('user')
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

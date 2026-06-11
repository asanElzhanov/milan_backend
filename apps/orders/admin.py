from django.contrib import admin
from .models import Cart, Order, OrderItem, OrderStatusHistory

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        'variant', 'product_name', 'product_slug', 'sku',
        'size_name', 'color_name', 'unit_price', 'quantity', 'total_price',
    )
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ('old_status', 'new_status', 'changed_by', 'comment', 'created_at')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'customer_name', 'email', 'phone', 'total_amount',
        'status', 'payment_status', 'delivery_method', 'created_at',
    )
    list_filter = ('status', 'payment_status', 'delivery_method', 'created_at')
    search_fields = ('order_number', 'email', 'phone', 'customer_name')
    readonly_fields = ('order_number', 'total_amount', 'created_at', 'updated_at')
    inlines = [OrderItemInline, OrderStatusHistoryInline]


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

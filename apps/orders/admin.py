from django.contrib import admin
from .models import Cart, Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        'variant', 'product_name', 'product_slug', 'sku',
        'size_name', 'color_name', 'unit_price', 'quantity', 'total_price',
    )
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number', 'customer_name', 'email', 'phone', 'total_amount',
        'status', 'payment_status', 'delivery_method', 'created_at',
    )
    list_filter = ('status', 'payment_status', 'delivery_method', 'created_at')
    search_fields = ('order_number', 'email', 'phone', 'customer_name')
    readonly_fields = ('order_number', 'total_amount', 'created_at', 'updated_at')
    inlines = [OrderItemInline]

admin.site.register(Cart)

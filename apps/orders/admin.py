from django.contrib import admin
from .models import Order, OrderItem, Cart, CartItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name', 'product_sku', 'color_name', 'size_value', 'unit_price', 'total_price')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'first_name', 'email', 'total', 'status', 'delivery_method', 'created_at')
    list_filter = ('status', 'delivery_method')
    search_fields = ('number', 'email', 'phone', 'first_name')
    readonly_fields = ('number', 'subtotal', 'total')
    inlines = [OrderItemInline]
    list_editable = ('status',)

admin.site.register(Cart)

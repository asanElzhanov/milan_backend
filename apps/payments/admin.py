from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'provider', 'status', 'amount', 'currency', 'created_at')
    list_filter = ('provider', 'status')
    search_fields = ('order__number', 'provider_payment_id')
    readonly_fields = ('provider_data',)

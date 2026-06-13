from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count, DecimalField, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html

from apps.orders.models import Order

from .models import Address, CustomerProfile, OTPCode, User


def _is_manager(user):
    return bool(
        user
        and user.is_active
        and user.is_staff
        and getattr(user, 'role', None) == User.Role.MANAGER
    )


class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    extra = 0
    max_num = 1
    fields = ('source', 'manager_comment', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return bool(obj and obj.role == User.Role.CUSTOMER and not hasattr(obj, 'customer_profile'))


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'email', 'phone', 'full_name', 'role',
        'is_active', 'is_staff', 'is_verified', 'date_joined',
    )
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'is_email_verified')
    search_fields = ('email', 'phone', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    readonly_fields = ('last_login', 'date_joined', 'updated_at')
    inlines = (CustomerProfileInline,)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone', 'avatar')}),
        ('Permissions', {
            'fields': (
                'role', 'is_active', 'is_staff', 'is_superuser',
                'is_email_verified', 'groups', 'user_permissions',
            )
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'phone', 'password1', 'password2', 'role', 'is_staff', 'is_superuser'),
        }),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'full_name', 'email', 'phone', 'source',
        'orders_count', 'total_orders_amount', 'last_order', 'orders_link',
    )
    list_filter = ('source', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'user__phone')
    autocomplete_fields = ('user',)
    readonly_fields = (
        'full_name', 'email', 'phone',
        'orders_count', 'total_orders_amount', 'last_order',
        'orders_link', 'created_at', 'updated_at',
    )
    fieldsets = (
        ('Клиент', {
            'fields': ('user', 'full_name', 'email', 'phone', 'source'),
        }),
        ('CRM', {
            'fields': ('manager_comment',),
        }),
        ('Заказы', {
            'fields': ('orders_count', 'total_orders_amount', 'last_order', 'orders_link'),
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    ordering = ('-created_at',)

    def get_queryset(self, request):
        paid_completed_orders = (
            Q(user__orders__status=Order.Status.COMPLETED)
            | Q(user__orders__payment_status=Order.PaymentStatus.PAID)
        )
        return (
            super().get_queryset(request)
            .filter(user__role=User.Role.CUSTOMER)
            .select_related('user')
            .annotate(
                _orders_count=Count('user__orders', distinct=True),
                _total_orders_amount=Coalesce(
                    Sum('user__orders__total_amount', filter=paid_completed_orders),
                    Value(Decimal('0.00')),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                _last_order=Max('user__orders__created_at'),
            )
        )

    def has_module_permission(self, request):
        if _is_manager(request.user):
            return True
        return super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        if _is_manager(request.user):
            return True
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if _is_manager(request.user):
            return True
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = set(super().get_readonly_fields(request, obj))
        readonly_fields.add('user')
        if _is_manager(request.user):
            editable_fields = {'source', 'manager_comment'}
            model_fields = {
                field.name
                for field in self.model._meta.fields
                if field.name not in editable_fields
            }
            readonly_fields.update(model_fields)
        return tuple(readonly_fields)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'user':
            kwargs['queryset'] = User.objects.filter(role=User.Role.CUSTOMER).order_by('email')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='имя')
    def full_name(self, obj):
        return obj.user.full_name

    @admin.display(description='email', ordering='user__email')
    def email(self, obj):
        return obj.user.email

    @admin.display(description='телефон', ordering='user__phone')
    def phone(self, obj):
        return obj.user.phone or ''

    @admin.display(description='заказов', ordering='_orders_count')
    def orders_count(self, obj):
        return getattr(obj, '_orders_count', 0)

    @admin.display(description='сумма оплаченных/завершённых заказов', ordering='_total_orders_amount')
    def total_orders_amount(self, obj):
        amount = getattr(obj, '_total_orders_amount', Decimal('0.00'))
        return f'{amount:.2f}'

    @admin.display(description='последний заказ', ordering='_last_order')
    def last_order(self, obj):
        return getattr(obj, '_last_order', None)

    @admin.display(description='заказы')
    def orders_link(self, obj):
        url = reverse('admin:orders_order_changelist')
        query = urlencode({'user__id__exact': obj.user_id})
        return format_html('<a href="{}?{}">Открыть заказы</a>', url, query)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'street', 'is_default')


admin.site.register(OTPCode)

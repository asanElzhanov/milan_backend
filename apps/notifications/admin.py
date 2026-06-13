from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'recipient', 'role', 'event_type',
        'is_read', 'created_at',
    )
    list_filter = ('event_type', 'role', 'is_read', 'created_at')
    search_fields = (
        'title', 'message', 'recipient__email',
        'recipient__first_name', 'recipient__last_name',
    )
    readonly_fields = (
        'title', 'message', 'recipient', 'role',
        'event_type', 'created_at', 'updated_at',
    )
    ordering = ('-created_at',)
    actions = ('mark_read', 'mark_unread')

    def has_add_permission(self, request):
        return False

    @admin.action(description='Пометить выбранные уведомления прочитанными')
    def mark_read(self, request, queryset):
        queryset.update(is_read=True)

    @admin.action(description='Пометить выбранные уведомления непрочитанными')
    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)

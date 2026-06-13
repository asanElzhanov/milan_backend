from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'recipient', 'role', 'event_type',
        'is_read', 'created_at',
    )
    list_filter = ('role', 'event_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

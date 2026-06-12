from django.contrib import admin

from .models import StaticPage


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'slug', 'content')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_active',)
    ordering = ('title',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Контент', {
            'fields': ('title', 'slug', 'content'),
        }),
        ('SEO', {
            'fields': ('seo_title', 'seo_description'),
        }),
        ('Публикация', {
            'fields': ('is_active',),
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

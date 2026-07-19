from django.contrib import admin

from .models import StaticPage


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'title_kz', 'title_en', 'slug', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title_ru', 'title_kz', 'title_en', 'slug', 'content_ru', 'content_kz', 'content_en')
    prepopulated_fields = {'slug': ('title_ru',)}
    list_editable = ('is_active',)
    ordering = ('title_ru',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Контент', {
            'fields': (
                'title_ru', 'title_kz', 'title_en', 'slug',
                'content_ru', 'content_kz', 'content_en',
            ),
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

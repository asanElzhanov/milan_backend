from django.contrib import admin

from .models import InfoDoc, StaticPage, StaticPageBlock


class StaticPageBlockInline(admin.StackedInline):
    model = StaticPageBlock
    extra = 1
    fields = (
        'sort_order', 'is_active',
        'title_ru', 'content_ru',
        'title_kz', 'content_kz',
        'title_en', 'content_en',
    )
    ordering = ('sort_order', 'id')


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'title_kz', 'title_en', 'slug', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title_ru', 'title_kz', 'title_en', 'slug', 'content_ru', 'content_kz', 'content_en')
    prepopulated_fields = {'slug': ('title_ru',)}
    list_editable = ('is_active',)
    ordering = ('title_ru',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = (StaticPageBlockInline,)
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


@admin.register(StaticPageBlock)
class StaticPageBlockAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'page', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('page', 'is_active')
    search_fields = (
        'title_ru', 'title_kz', 'title_en',
        'content_ru', 'content_kz', 'content_en',
    )
    list_editable = ('sort_order', 'is_active')
    ordering = ('page', 'sort_order', 'id')
    autocomplete_fields = ('page',)


@admin.register(InfoDoc)
class InfoDocAdmin(admin.ModelAdmin):
    list_display = ('title_ru', 'title_kz', 'title_en', 'sort_order', 'is_active', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title_ru', 'title_kz', 'title_en')
    list_editable = ('sort_order', 'is_active')
    ordering = ('sort_order', 'id')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Документ', {
            'fields': ('title_ru', 'title_kz', 'title_en', 'file'),
        }),
        ('Публикация', {
            'fields': ('sort_order', 'is_active'),
        }),
        ('Системные поля', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

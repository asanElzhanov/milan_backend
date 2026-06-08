from django.contrib import admin
from mptt.admin import MPTTModelAdmin
from .models import Category, Brand, Product, ProductImage, ProductVariant, Color, Size, Review, Banner, Promo

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'brand', 'price', 'old_price', 'is_active', 'is_new')
    list_filter = ('is_active', 'is_new', 'category', 'brand', 'season')
    search_fields = ('name', 'sku', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'is_active', 'is_new')

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1

@admin.register(Category)
class CategoryAdmin(MPTTModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active', 'sort_order')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    ordering = ('tree_id', 'lft')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'logo')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'hex_code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug', 'hex_code')
    ordering = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ('value', 'size_type', 'sort_order', 'is_active')
    list_filter = ('size_type', 'is_active')
    search_fields = ('value',)
    ordering = ('size_type', 'sort_order', 'value')
    list_editable = ('sort_order', 'is_active')
    readonly_fields = ('created_at', 'updated_at')


admin.site.register(Review)
admin.site.register(Banner)
admin.site.register(Promo)

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
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

admin.site.register(Color)
admin.site.register(Size)
admin.site.register(Review)
admin.site.register(Banner)
admin.site.register(Promo)

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from mptt.managers import TreeManager
from mptt.models import MPTTModel, TreeForeignKey


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class CategoryManager(TreeManager.from_queryset(CategoryQuerySet)):
    pass


class Category(MPTTModel):
    """Дерево категорий: Обувь → Кроссовки"""
    name = models.CharField(_('название'), max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    parent = TreeForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children', verbose_name=_('родительская категория')
    )
    image = models.ImageField(_('изображение'), upload_to='categories/', blank=True, null=True)
    description = models.TextField(_('описание'), blank=True)
    is_active = models.BooleanField(_('активна'), default=True)
    sort_order = models.PositiveSmallIntegerField(_('порядок'), default=0)
    seo_title = models.CharField(_('SEO title'), max_length=200, blank=True)
    seo_description = models.TextField(_('SEO description'), blank=True)
    seo_keywords = models.CharField(_('SEO keywords'), max_length=255, blank=True)
    created_at = models.DateTimeField(_('создана'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлена'), auto_now=True)

    objects = CategoryManager()

    class MPTTMeta:
        order_insertion_by = ['sort_order', 'name']

    class Meta:
        verbose_name = _('категория')
        verbose_name_plural = _('категории')
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class Brand(models.Model):
    name = models.CharField(_('название'), max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    logo = models.ImageField(_('лого'), upload_to='brands/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('бренд')
        verbose_name_plural = _('бренды')
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Товар"""
    class Season(models.TextChoices):
        SPRING_SUMMER = 'ss', _('Весна/Лето')
        AUTUMN_WINTER = 'aw', _('Осень/Зима')
        ALL_SEASON = 'all', _('Всесезонный')

    sku = models.CharField(_('артикул'), max_length=100, unique=True)
    name = models.CharField(_('название'), max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True,
        related_name='products', verbose_name=_('категория')
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products', verbose_name=_('бренд')
    )
    description = models.TextField(_('описание'), blank=True)
    composition = models.TextField(_('состав'), blank=True)
    material = models.CharField(_('материал'), max_length=100, blank=True)
    season = models.CharField(_('сезон'), max_length=10, choices=Season.choices, blank=True)

    # Цены
    price = models.DecimalField(_('цена'), max_digits=10, decimal_places=2)
    old_price = models.DecimalField(_('старая цена'), max_digits=10, decimal_places=2, null=True, blank=True)

    # Статус
    is_active = models.BooleanField(_('активен'), default=True)
    is_new = models.BooleanField(_('новинка'), default=False)
    is_featured = models.BooleanField(_('рекомендован'), default=False)

    # Счётчики (денормализованы для скорости)
    views_count = models.PositiveIntegerField(default=0)
    orders_count = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    reviews_count = models.PositiveIntegerField(default=0)

    # SEO
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('товар')
        verbose_name_plural = _('товары')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['brand', 'is_active']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.name

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return int((1 - self.price / self.old_price) * 100)
        return 0

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f'{self.brand} {self.name}', allow_unicode=True)
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(_('изображение'), upload_to='products/')
    alt = models.CharField(max_length=200, blank=True)
    is_main = models.BooleanField(_('главное фото'), default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order']

    def save(self, *args, **kwargs):
        if self.is_main:
            ProductImage.objects.filter(product=self.product, is_main=True).update(is_main=False)
        super().save(*args, **kwargs)


class ProductVideo(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(upload_to='products/videos/', blank=True)
    youtube_url = models.URLField(blank=True)
    thumbnail = models.ImageField(upload_to='products/video_thumbs/', blank=True, null=True)

    class Meta:
        verbose_name = _('видео товара')


class Color(models.Model):
    name = models.CharField(_('название'), max_length=50)
    hex_code = models.CharField(_('hex'), max_length=7)

    class Meta:
        verbose_name = _('цвет')

    def __str__(self):
        return self.name


class Size(models.Model):
    """Размер (EUR числовые или буквенные S/M/L)"""
    value = models.CharField(_('значение'), max_length=10)  # "37", "38.5", "M"
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _('размер')
        ordering = ['sort_order', 'value']

    def __str__(self):
        return self.value


class ProductVariant(models.Model):
    """Вариант товара: конкретный цвет + размер + остаток"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    size = models.ForeignKey(Size, on_delete=models.SET_NULL, null=True, blank=True)
    stock = models.PositiveIntegerField(_('остаток'), default=0)
    sku_variant = models.CharField(_('артикул варианта'), max_length=100, blank=True)
    extra_price = models.DecimalField(_('доп. цена'), max_digits=8, decimal_places=2, default=0)

    class Meta:
        verbose_name = _('вариант товара')
        unique_together = ('product', 'color', 'size')
        indexes = [models.Index(fields=['product', 'stock'])]

    def __str__(self):
        return f'{self.product} | {self.color} | {self.size}'

    @property
    def is_available(self):
        return self.stock > 0

    @property
    def final_price(self):
        return self.product.price + self.extra_price


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    text = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('отзыв')
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.product} — {self.rating}★'


class ReviewImage(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='reviews/')


class Banner(models.Model):
    class Position(models.TextChoices):
        HERO = 'hero', 'Главный баннер'
        MID = 'mid', 'Средний'
        PROMO = 'promo', 'Промо'

    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    image = models.ImageField(upload_to='banners/')
    image_mobile = models.ImageField(upload_to='banners/', blank=True, null=True)
    link = models.CharField(max_length=255, blank=True)
    position = models.CharField(max_length=10, choices=Position.choices, default=Position.HERO)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('баннер')
        ordering = ['sort_order']


class Promo(models.Model):
    """Промокод"""
    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Процент'
        FIXED = 'fixed', 'Фиксированная сумма'

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('промокод')

    def __str__(self):
        return self.code

    def is_valid(self, order_amount=0):
        from django.utils import timezone
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        if order_amount < self.min_order_amount:
            return False
        return True

    def calculate_discount(self, amount):
        if self.discount_type == self.DiscountType.PERCENT:
            return (amount * self.discount_value / 100).quantize(amount)
        return min(self.discount_value, amount)

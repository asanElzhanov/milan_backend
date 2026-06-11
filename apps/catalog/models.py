from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
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
    is_active = models.BooleanField(_('активен'), default=True)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлен'), auto_now=True)

    class Meta:
        verbose_name = _('бренд')
        verbose_name_plural = _('бренды')
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


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
    price = models.DecimalField(
        _('цена'),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    old_price = models.DecimalField(
        _('старая цена'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
    )

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
    seo_title = models.CharField(_('SEO title'), max_length=200, blank=True)
    seo_description = models.TextField(_('SEO description'), blank=True)
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
            models.Index(fields=['is_active']),
            models.Index(fields=['is_active', 'price'], name='cat_product_active_price_idx'),
            models.Index(fields=['is_new'], name='catalog_product_is_new_idx'),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['brand', 'is_active']),
            models.Index(fields=['-created_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name='product_price_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(old_price__isnull=True) | models.Q(old_price__gte=models.F('price')),
                name='product_old_price_gte_price',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def discount_percent(self) -> int:
        if self.old_price and self.old_price > self.price:
            return int((1 - self.price / self.old_price) * 100)
        return 0

    @property
    def discount(self) -> int:
        return self.discount_percent

    @property
    def is_sale(self) -> bool:
        return self.discount_percent > 0

    def clean(self):
        super().clean()
        errors = {}
        if self.price is not None and self.price < 0:
            errors['price'] = _('Цена не может быть отрицательной.')
        if (
            self.old_price is not None
            and self.price is not None
            and self.old_price < self.price
        ):
            errors['old_price'] = _('Старая цена не может быть меньше текущей цены.')
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base_slug = slugify(self.name, allow_unicode=True) or 'product'
        slug = base_slug
        counter = 2
        queryset = Product.objects.filter(slug=slug)
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        while queryset.exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
            queryset = Product.objects.filter(slug=slug)
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)
        return slug


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(_('изображение'), upload_to='products/images/%Y/%m/%d/')
    alt_text = models.CharField(_('alt text'), max_length=200, blank=True)
    is_main = models.BooleanField(_('главное фото'), default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(_('создано'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлено'), auto_now=True)

    class Meta:
        verbose_name = _('изображение товара')
        verbose_name_plural = _('изображения товаров')
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['product', 'sort_order']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['product'],
                condition=models.Q(is_main=True),
                name='unique_main_image_per_product',
            ),
        ]

    def __str__(self):
        return f'{self.product} image #{self.pk or "new"}'

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_main:
                ProductImage.objects.filter(
                    product=self.product,
                    is_main=True,
                ).exclude(pk=self.pk).update(is_main=False)
            super().save(*args, **kwargs)


class ProductVideo(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(upload_to='products/videos/', blank=True)
    youtube_url = models.URLField(blank=True)
    thumbnail = models.ImageField(upload_to='products/video_thumbs/', blank=True, null=True)

    class Meta:
        verbose_name = _('видео товара')


class ProductMedia(models.Model):
    """Дополнительные медиа товара. ProductImage остается основной галереей изображений."""
    class MediaType(models.TextChoices):
        IMAGE = 'image', _('Изображение')
        VIDEO = 'video', _('Видео')

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='media')
    media_type = models.CharField(_('тип медиа'), max_length=10, choices=MediaType.choices)
    file = models.FileField(_('файл'), upload_to='products/media/%Y/%m/%d/', blank=True)
    url = models.URLField(_('ссылка'), blank=True)
    title = models.CharField(_('заголовок'), max_length=200, blank=True)
    alt_text = models.CharField(_('alt text'), max_length=200, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(_('активно'), default=True)
    created_at = models.DateTimeField(_('создано'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлено'), auto_now=True)

    class Meta:
        verbose_name = _('медиа товара')
        verbose_name_plural = _('медиа товаров')
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['product', 'sort_order'], name='product_media_product_sort_idx'),
            models.Index(fields=['media_type'], name='product_media_type_idx'),
            models.Index(fields=['is_active'], name='product_media_active_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(file='') | ~models.Q(url=''),
                name='product_media_file_or_url_required',
            ),
        ]

    def __str__(self):
        return f'{self.product} | {self.media_type} #{self.pk or "new"}'

    def clean(self):
        super().clean()
        if not self.file and not self.url:
            raise ValidationError(_('Укажите файл или ссылку для медиа товара.'))


class Color(models.Model):
    name = models.CharField(_('название'), max_length=50)
    slug = models.SlugField(max_length=80, unique=True)
    hex_code = models.CharField(
        _('hex'),
        max_length=7,
        validators=[
            RegexValidator(
                regex=r'^#[0-9A-Fa-f]{6}$',
                message=_('Введите HEX-цвет в формате #FFFFFF.'),
            ),
        ],
    )
    is_active = models.BooleanField(_('активен'), default=True)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлен'), auto_now=True)

    class Meta:
        verbose_name = _('цвет')
        verbose_name_plural = _('цвета')
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class Size(models.Model):
    """Размер (EUR числовые или буквенные S/M/L)"""
    class SizeType(models.TextChoices):
        SHOES = 'shoes', _('Обувь')
        CLOTHES = 'clothes', _('Одежда')
        ACCESSORIES = 'accessories', _('Аксессуары')

    value = models.CharField(_('значение'), max_length=20)  # "37", "38.5", "M", "One Size"
    size_type = models.CharField(_('тип размера'), max_length=20, choices=SizeType.choices)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(_('активен'), default=True)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлен'), auto_now=True)

    class Meta:
        verbose_name = _('размер')
        verbose_name_plural = _('размеры')
        ordering = ['size_type', 'sort_order', 'value']
        constraints = [
            models.UniqueConstraint(fields=['value', 'size_type'], name='unique_size_value_type'),
        ]

    def __str__(self):
        return f'{self.size_type}: {self.value}'


class ProductVariant(models.Model):
    """Вариант товара: конкретный цвет + размер + остаток"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    size = models.ForeignKey(Size, on_delete=models.SET_NULL, null=True, blank=True)
    sku = models.CharField(_('артикул варианта'), max_length=100, unique=True)
    stock_quantity = models.PositiveIntegerField(_('остаток'), default=0)
    variant_price = models.DecimalField(
        _('цена варианта'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    is_active = models.BooleanField(_('активен'), default=True)
    created_at = models.DateTimeField(_('создан'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлен'), auto_now=True)

    class Meta:
        verbose_name = _('вариант товара')
        verbose_name_plural = _('варианты товаров')
        unique_together = ('product', 'color', 'size')
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['product']),
            models.Index(fields=['is_active']),
            models.Index(fields=['stock_quantity']),
            models.Index(fields=['product', 'stock_quantity'], name='catalog_pro_product_ee4f5c_idx'),
            models.Index(fields=['product', 'is_active', 'stock_quantity'], name='cat_var_stock_lookup_idx'),
            models.Index(fields=['size', 'is_active', 'product'], name='cat_var_size_lookup_idx'),
            models.Index(fields=['color', 'is_active', 'product'], name='cat_var_color_lookup_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(stock_quantity__gte=0),
                name='product_variant_stock_non_negative',
            ),
            models.CheckConstraint(
                check=models.Q(variant_price__isnull=True) | models.Q(variant_price__gte=0),
                name='product_variant_price_non_negative',
            ),
        ]

    def __str__(self):
        return f'{self.product} | {self.sku}'

    @property
    def in_stock(self) -> bool:
        return self.stock_quantity > 0 and self.is_active

    @property
    def is_available(self) -> bool:
        return self.in_stock

    @property
    def final_price(self) -> Decimal:
        return self.variant_price if self.variant_price is not None else self.product.price

    def clean(self):
        super().clean()
        errors = {}
        if self.stock_quantity is not None and self.stock_quantity < 0:
            errors['stock_quantity'] = _('Остаток не может быть отрицательным.')
        if self.variant_price is not None and self.variant_price < 0:
            errors['variant_price'] = _('Цена варианта не может быть отрицательной.')
        if errors:
            raise ValidationError(errors)


class StockMovement(models.Model):
    """Append-only журнал движений остатков по варианту товара."""
    class OperationType(models.TextChoices):
        INCOME = 'income', _('Приход')
        SALE = 'sale', _('Продажа')
        RETURN = 'return', _('Возврат')
        MANUAL_ADJUSTMENT = 'manual_adjustment', _('Ручная корректировка')
        ORDER_CANCEL = 'order_cancel', _('Отмена заказа')

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name='stock_movements',
        verbose_name=_('вариант товара'),
    )
    quantity = models.PositiveIntegerField(
        _('количество'),
        validators=[MinValueValidator(1)],
    )
    operation_type = models.CharField(
        _('тип операции'),
        max_length=32,
        choices=OperationType.choices,
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
        verbose_name=_('пользователь'),
    )
    comment = models.TextField(_('комментарий'), blank=True)
    created_at = models.DateTimeField(_('создано'), auto_now_add=True)

    class Meta:
        verbose_name = _('движение остатка')
        verbose_name_plural = _('движения остатков')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['variant']),
            models.Index(fields=['operation_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['user']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name='stock_movement_quantity_positive',
            ),
        ]

    def __str__(self):
        return f'{self.variant.sku} | {self.operation_type} | {self.quantity}'


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

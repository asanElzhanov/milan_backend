from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class StaticPageQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class StaticPage(models.Model):
    slug = models.SlugField(_('slug'), max_length=220, unique=True)
    title_ru = models.CharField(_('название'), max_length=200)
    title_kz = models.CharField(_('название (каз.)'), max_length=200, blank=True, default='')
    title_en = models.CharField(_('название (англ.)'), max_length=200, blank=True, default='')
    content_ru = models.TextField(_('контент'))
    content_kz = models.TextField(_('контент (каз.)'), blank=True, default='')
    content_en = models.TextField(_('контент (англ.)'), blank=True, default='')
    seo_title = models.CharField(_('SEO title'), max_length=200, blank=True)
    seo_description = models.TextField(_('SEO description'), blank=True)
    is_active = models.BooleanField(_('активна'), default=True)
    created_at = models.DateTimeField(_('создана'), auto_now_add=True)
    updated_at = models.DateTimeField(_('обновлена'), auto_now=True)

    objects = StaticPageQuerySet.as_manager()

    class Meta:
        verbose_name = _('статическая страница')
        verbose_name_plural = _('статические страницы')
        ordering = ['title_ru']
        indexes = [
            models.Index(fields=['slug'], name='cms_static_slug_idx'),
            models.Index(fields=['is_active'], name='cms_static_active_idx'),
        ]

    def __str__(self):
        return self.title_ru

    def clean(self):
        super().clean()
        if self.slug:
            self.slug = self.slug.strip()
        if self.title_ru:
            self.title_ru = self.title_ru.strip()
        if self.seo_title:
            self.seo_title = self.seo_title.strip()
        if not self.title_ru:
            raise ValidationError({'title_ru': _('Название страницы обязательно.')})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base_slug = slugify(self.title_ru, allow_unicode=True) or 'page'
        slug = base_slug
        counter = 2
        queryset = StaticPage.objects.filter(slug=slug)
        if self.pk:
            queryset = queryset.exclude(pk=self.pk)
        while queryset.exists():
            slug = f'{base_slug}-{counter}'
            counter += 1
            queryset = StaticPage.objects.filter(slug=slug)
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)
        return slug


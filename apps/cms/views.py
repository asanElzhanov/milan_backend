from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, permissions

from .models import InfoDoc, StaticPage, StaticPageBlock
from .serializers import (
    InfoDocSerializer,
    StaticPageDetailSerializer,
    StaticPageListSerializer,
)


class StaticPageListView(generics.ListAPIView):
    """GET /cms/pages/"""
    serializer_class = StaticPageListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return StaticPage.objects.active().only(
            'id', 'slug', 'title_ru', 'title_kz', 'title_en',
        ).order_by('title_ru')

    @extend_schema(
        tags=['CMS / Pages'],
        summary='Список активных статических страниц',
        responses={200: StaticPageListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class InfoDocListView(generics.ListAPIView):
    """GET /cms/info-docs/"""
    serializer_class = InfoDocSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        return InfoDoc.objects.active().only(
            'id', 'title_ru', 'title_kz', 'title_en', 'file', 'sort_order',
        ).order_by('sort_order', 'id')

    @extend_schema(
        tags=['CMS / Pages'],
        summary='Список информационных документов',
        responses={200: InfoDocSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class StaticPageDetailView(generics.RetrieveAPIView):
    """GET /cms/pages/<slug>/"""
    serializer_class = StaticPageDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        active_blocks = StaticPageBlock.objects.active().only(
            'id', 'page_id',
            'title_ru', 'title_kz', 'title_en',
            'content_ru', 'content_kz', 'content_en',
            'sort_order',
        ).order_by('sort_order', 'id')
        return StaticPage.objects.active().only(
            'id', 'slug',
            'title_ru', 'title_kz', 'title_en',
            'content_ru', 'content_kz', 'content_en',
            'seo_title', 'seo_description',
        ).prefetch_related(Prefetch('blocks', queryset=active_blocks))

    @extend_schema(
        tags=['CMS / Pages'],
        summary='Активная статическая страница по slug',
        responses={
            200: StaticPageDetailSerializer,
            404: OpenApiResponse(description='Страница не найдена'),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

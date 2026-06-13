from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, permissions

from .models import StaticPage
from .serializers import StaticPageDetailSerializer, StaticPageListSerializer


class StaticPageListView(generics.ListAPIView):
    """GET /cms/pages/"""
    serializer_class = StaticPageListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return StaticPage.objects.active().only('id', 'slug', 'title').order_by('title')

    @extend_schema(
        tags=['CMS / Pages'],
        summary='Список активных статических страниц',
        responses={200: StaticPageListSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class StaticPageDetailView(generics.RetrieveAPIView):
    """GET /cms/pages/<slug>/"""
    serializer_class = StaticPageDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return StaticPage.objects.active().only(
            'id', 'slug', 'title', 'content', 'seo_title', 'seo_description',
        )

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
